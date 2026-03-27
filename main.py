# import cv2
# import face_recognition
# import numpy as np
# import requests

# # 1. Load image
# raw_img = cv2.imread("known.jpg")
# if raw_img is None:
#     print("Error: Could not find 'known.jpg' ❌")
#     exit()

# # 2. Convert BGR to RGB
# rgb_img = cv2.cvtColor(raw_img, cv2.COLOR_BGR2RGB)

# # 3. FORCE CONTIGUOUS MEMORY LAYOUT (The likely fix)
# # This reorganizes the underlying memory bytes for dlib
# known_image = np.ascontiguousarray(rgb_img)

# # 4. Double check the type and order
# print(f"DEBUG: Shape {known_image.shape}, Dtype {known_image.dtype}")
# print(f"DEBUG: Is Contiguous? {known_image.flags['C_CONTIGUOUS']}")

# try:
#     # 5. Get encodings
#     encodings = face_recognition.face_encodings(known_image)
    
#     if len(encodings) == 0:
#         print("No face found in 'known.jpg' ❌")
#         exit()
        
#     known_encoding = encodings[0]
#     print("Reference face encoded successfully! ✅")

# except Exception as e:
#     print(f"Critical Error: {e}")


# # http://10.98.104.43/action?go='on'


# # Start webcam
# video_capture = cv2.VideoCapture(0)
# # video_capture = cv2.VideoCapture("http://10.98.104.43/stream")
# print("Starting camera... Press 'q' to quit.")


# while True:
#     ret, frame = video_capture.read()
#     if not ret: break

#     # 1. Prepare frame
#     rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])

#     # 2. Manual Detection
#     face_locations = face_recognition.face_locations(rgb_frame)
    
#     # 3. MANUAL ENCODING (Replacing the crashing function)
#     face_encodings = []
#     if len(face_locations) > 0:
#         # This reaches deeper into the library to bypass the argument bug
#         raw_landmarks = face_recognition.api._raw_face_landmarks(rgb_frame, face_locations)
        
#         for landmark in raw_landmarks:
#             # We call the model directly. 
#             # Note: We are NOT passing num_jitters here to avoid the TypeError
#             encoding = face_recognition.api.face_encoder.compute_face_descriptor(rgb_frame, landmark)
#             face_encodings.append(np.array(encoding))

#     # 4. Compare faces
#     for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
#         matches = face_recognition.compare_faces([known_encoding], face_encoding)
        
#         label = "AUTHORIZED ✅" if matches[0] else "UNKNOWN ❌"
#         color = (0, 255, 0) if matches[0] else (0, 0, 255)
#         if matches[0]:
#             requests.get("http://10.98.104.222/action?go=on")
#             print("Unlocked")
#         else:
#             requests.get("http://10.98.104.222/action?go=off")



#         cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
#         cv2.putText(frame, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

#     cv2.imshow("Face Unlock System", frame)
#     if cv2.waitKey(1) & 0xFF == ord("q"): break

# video_capture.release()
# cv2.destroyAllWindows()







import cv2
import face_recognition
import numpy as np
import requests
import threading
from queue import Queue

# =========================
# STREAM READER THREAD (FIXED FOR MJPEG)
# =========================
frame_queue = Queue(maxsize=5)
stop_flag = False

def read_stream():
    global stop_flag
    stream_url = "http://10.98.104.43/stream"
    
    try:
        stream = requests.get(stream_url, stream=True, timeout=5)
        print("✅ Thread connected, status:", stream.status_code)
    except Exception as e:
        print("❌ Thread connection failed:", e)
        return
    
    # MJPEG boundary detection
    boundary = None
    buffer = b""
    
    for chunk in stream.iter_content(chunk_size=4096):
        if stop_flag:
            break
        if not chunk:
            continue
        
        buffer += chunk
        
        # Auto-detect boundary from Content-Type header
        if boundary is None and stream.headers.get('Content-Type', '').startswith('multipart/x-mixed-replace'):
            # Try to extract boundary from header
            ct = stream.headers['Content-Type']
            if 'boundary=' in ct:
                boundary = ct.split('boundary=')[-1].strip().encode()
                print(f"✅ Detected boundary: {boundary.decode()}")
        
        # If we have a boundary, parse multipart
        if boundary:
            while True:
                # Find boundary
                start = buffer.find(b'--' + boundary)
                if start == -1:
                    break
                
                # Find end of this part
                end = buffer.find(b'--' + boundary, start + len(boundary) + 2)
                if end == -1:
                    break
                
                # Extract JPEG data (skip headers)
                part = buffer[start:end]
                jpeg_start = part.find(b'\xff\xd8')
                jpeg_end = part.rfind(b'\xff\xd9')
                
                if jpeg_start != -1 and jpeg_end != -1 and jpeg_end > jpeg_start:
                    jpg = part[jpeg_start:jpeg_end+2]
                    
                    try:
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame = cv2.resize(frame, (480, 360))
                            if frame_queue.full():
                                frame_queue.get()
                            frame_queue.put(frame)
                            print("✅ Frame decoded")  # Debug
                    except Exception as e:
                        print("❌ Frame decode error:", e)
                
                # Remove processed part
                buffer = buffer[end:]
        else:
            # Fallback: try raw JPEG detection
            a = buffer.find(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9')
            
            if a != -1 and b != -1 and b > a:
                jpg = buffer[a:b+2]
                buffer = buffer[b+2:]
                
                if len(jpg) > 100:
                    try:
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame = cv2.resize(frame, (480, 360))
                            if frame_queue.full():
                                frame_queue.get()
                            frame_queue.put(frame)
                            print("✅ Raw JPEG frame decoded")  # Debug
                    except Exception as e:
                        print("❌ Raw JPEG decode error:", e)

# =========================
# LOAD KNOWN FACE
# =========================
raw_img = cv2.imread("known.jpg")
if raw_img is None:
    print("Error: Could not find 'known.jpg' ❌")
    exit()

rgb_img = cv2.cvtColor(raw_img, cv2.COLOR_BGR2RGB)
known_image = np.ascontiguousarray(rgb_img)
encodings = face_recognition.face_encodings(known_image)

if len(encodings) == 0:
    print("No face found in 'known.jpg' ❌")
    exit()

known_encoding = encodings  # ✅ Get FIRST encoding only
print("Reference face encoded successfully! ✅")


# =========================
# START STREAM THREAD
# =========================
stream_thread = threading.Thread(target=read_stream, daemon=True)
stream_thread.start()
print("✅ Stream connected. Starting video...")

# =========================
# MAIN PROCESSING LOOP
# =========================
frame_count = 0
face_locations = []
face_encodings = []

while True:
    try:
        frame = frame_queue.get(timeout=2)
    except:
        print("⚠️ No frames received")
        continue
    
    frame_count += 1
    process_this_frame = (frame_count % 3 == 0)
    
    rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])
    
    if process_this_frame:
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")
        face_encodings = []
        
        if len(face_locations) > 0:
            raw_landmarks = face_recognition.api._raw_face_landmarks(rgb_frame, face_locations)
            for landmark in raw_landmarks:
                encoding = face_recognition.api.face_encoder.compute_face_descriptor(
                    rgb_frame, landmark
                )
                face_encodings.append(np.array(encoding))
    
    # Draw results
    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        matches = face_recognition.compare_faces([known_encoding], face_encoding, tolerance=0.5)
        is_match = matches[0]  # ✅ Get first element from matches list
        label = "AUTHORIZED ✅" if is_match else "UNKNOWN ❌"
        color = (0, 255, 0) if is_match else (0, 0, 255)


        if is_match:
            requests.get("http://10.98.104.222/action?go=on")
            print("🔓 Unlocked")
        
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)

        cv2.putText(frame, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    
    cv2.imshow("Face Unlock System", frame)
    
    if cv2.waitKey(30) & 0xFF == ord('q'):
        stop_flag = True
        break

cv2.destroyAllWindows()






# import cv2
# import face_recognition
# import numpy as np
# import requests
# import threading
# from queue import Queue
# import os
# from pathlib import Path

# # =========================
# # CONFIGURATION
# # =========================
# KNOWN_FACES_DIR = "known"
# os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

# # =========================
# # STREAM READER THREAD (FIXED FOR MJPEG)
# # =========================
# frame_queue = Queue(maxsize=5)
# stop_flag = False
# current_frame = None

# def read_stream():
#     global stop_flag, current_frame
#     stream_url = "http://10.98.104.43/stream"
    
#     try:
#         stream = requests.get(stream_url, stream=True, timeout=5)
#         print("✅ Thread connected, status:", stream.status_code)
#     except Exception as e:
#         print("❌ Thread connection failed:", e)
#         return
    
#     boundary = None
#     buffer = b""
    
#     for chunk in stream.iter_content(chunk_size=4096):
#         if stop_flag:
#             break
#         if not chunk:
#             continue
        
#         buffer += chunk
        
#         if boundary is None and stream.headers.get('Content-Type', '').startswith('multipart/x-mixed-replace'):
#             ct = stream.headers['Content-Type']
#             if 'boundary=' in ct:
#                 boundary = ct.split('boundary=')[-1].strip().encode()
#                 print(f"✅ Detected boundary: {boundary.decode()}")
        
#         if boundary:
#             while True:
#                 start = buffer.find(b'--' + boundary)
#                 if start == -1:
#                     break
                
#                 end = buffer.find(b'--' + boundary, start + len(boundary) + 2)
#                 if end == -1:
#                     break
                
#                 part = buffer[start:end]
#                 jpeg_start = part.find(b'\xff\xd8')
#                 jpeg_end = part.rfind(b'\xff\xd9')
                
#                 if jpeg_start != -1 and jpeg_end != -1 and jpeg_end > jpeg_start:
#                     jpg = part[jpeg_start:jpeg_end+2]
                    
#                     try:
#                         frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
#                         if frame is not None:
#                             frame = cv2.resize(frame, (480, 360))
#                             current_frame = frame.copy()
#                             if frame_queue.full():
#                                 frame_queue.get()
#                             frame_queue.put(frame)
#                     except Exception as e:
#                         pass
                
#                 buffer = buffer[end:]
#         else:
#             a = buffer.find(b'\xff\xd8')
#             b = buffer.find(b'\xff\xd9')
            
#             if a != -1 and b != -1 and b > a:
#                 jpg = buffer[a:b+2]
#                 buffer = buffer[b+2:]
                
#                 if len(jpg) > 100:
#                     try:
#                         frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
#                         if frame is not None:
#                             frame = cv2.resize(frame, (480, 360))
#                             current_frame = frame.copy()
#                             if frame_queue.full():
#                                 frame_queue.get()
#                             frame_queue.put(frame)
#                     except Exception as e:
#                         pass

# # =========================
# # LOAD ALL KNOWN FACES FROM FOLDER
# # =========================
# def load_known_faces():
#     known_encodings = []
#     known_names = []
    
#     image_files = list(Path(KNOWN_FACES_DIR).glob("*.jpg")) + \
#                   list(Path(KNOWN_FACES_DIR).glob("*.png")) + \
#                   list(Path(KNOWN_FACES_DIR).glob("*.jpeg"))
    
#     if not image_files:
#         print(f"⚠️ No images found in {KNOWN_FACES_DIR}")
#         return known_encodings, known_names
    
#     for image_path in image_files:
#         print(f"Loading: {image_path.name}")
        
#         raw_img = cv2.imread(str(image_path))
#         if raw_img is None:
#             print(f"  ❌ Failed to load {image_path.name}")
#             continue
        
#         rgb_img = cv2.cvtColor(raw_img, cv2.COLOR_BGR2RGB)
#         encodings = face_recognition.face_encodings(rgb_img)
        
#         if len(encodings) == 0:
#             print(f"  ⚠️ No face found in {image_path.name}")
#             continue
        
#         known_encodings.append(encodings)
#         known_names.append(image_path.stem)
#         print(f"  ✅ Face encoded from {image_path.name}")
    
#     return known_encodings, known_names

# # =========================
# # CAPTURE AND SAVE IMAGE
# # =========================
# def capture_image():
#     global current_frame
    
#     if current_frame is None:
#         print("❌ No frame available to capture")
#         return
    
#     timestamp = cv2.getTickCount()
#     filename = os.path.join(KNOWN_FACES_DIR, f"face_{timestamp}.jpg")
    
#     cv2.imwrite(filename, current_frame)
#     print(f"✅ Image saved: {filename}")

# # =========================
# # START STREAM THREAD
# # =========================
# stream_thread = threading.Thread(target=read_stream, daemon=True)
# stream_thread.start()
# print("✅ Stream connected. Starting video...")
# print("📸 Press 'I' to capture and save image")
# print("🔄 Press 'R' to reload known faces")
# print("❌ Press 'Q' to quit")

# # =========================
# # LOAD INITIAL KNOWN FACES
# # =========================
# known_encodings, known_names = load_known_faces()

# # =========================
# # MAIN PROCESSING LOOP
# # =========================
# frame_count = 0
# face_locations = []
# face_encodings = []

# while True:
#     try:
#         frame = frame_queue.get(timeout=2)
#     except:
#         print("⚠️ No frames received")
#         continue
    
#     frame_count += 1
#     process_this_frame = (frame_count % 3 == 0)
    
#     rgb_frame = np.ascontiguousarray(frame[:, :, ::-1])
    
#     if process_this_frame:
#         face_locations = face_recognition.face_locations(rgb_frame, model="hog")
#         face_encodings = []
        
#         if len(face_locations) > 0:
#             raw_landmarks = face_recognition.api._raw_face_landmarks(rgb_frame, face_locations)
#             for landmark in raw_landmarks:
#                 encoding = face_recognition.api.face_encoder.compute_face_descriptor(
#                     rgb_frame, landmark
#                 )
#                 face_encodings.append(np.array(encoding))
    
#     # Draw results
#     for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        
#         # Compare with all known faces
#         matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.5)
#         distances = face_recognition.face_distance(known_encodings, face_encoding)
        
#         best_match_index = np.argmin(distances) if len(distances) > 0 else -1
        
#         if best_match_index >= 0 and matches[best_match_index]:
#             name = known_names[best_match_index]
#             label = f"✅ {name}"
#             color = (0, 255, 0)
            
#             requests.get("http://10.98.104.222/action?go=on")
#             print(f"🔓 Unlocked - Match: {name}")
#         else:
#             label = "❌ UNKNOWN"
#             color = (0, 0, 255)
        
#         cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
#         cv2.putText(frame, label, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
#     cv2.imshow("Face Unlock System", frame)
    
#     key = cv2.waitKey(30) & 0xFF
    
#     if key == ord('q'):
#         stop_flag = True
#         break
#     elif key == ord('i'):
#         capture_image()
#     elif key == ord('r'):
#         print("🔄 Reloading known faces...")
#         known_encodings, known_names = load_known_faces()
#         print(f"✅ Loaded {len(known_encodings)} known faces")

# cv2.destroyAllWindows()