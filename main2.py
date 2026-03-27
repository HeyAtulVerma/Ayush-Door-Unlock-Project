import cv2
import face_recognition
import numpy as np
import requests
import threading
import time
from queue import Queue

# =========================
# STREAM READER THREAD (MJPEG FIXED)
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
    
    boundary = None
    buffer = b""
    
    for chunk in stream.iter_content(chunk_size=4096):
        if stop_flag:
            break
        if not chunk:
            continue
        
        buffer += chunk
        
        # Detect boundary
        if boundary is None and stream.headers.get('Content-Type', '').startswith('multipart/x-mixed-replace'):
            ct = stream.headers['Content-Type']
            if 'boundary=' in ct:
                boundary = ct.split('boundary=')[-1].strip().encode()
                print(f"✅ Detected boundary: {boundary.decode()}")
        
        # Parse MJPEG
        if boundary:
            while True:
                start = buffer.find(b'--' + boundary)
                if start == -1:
                    break
                
                end = buffer.find(b'--' + boundary, start + len(boundary) + 2)
                if end == -1:
                    break
                
                part = buffer[start:end]
                jpeg_start = part.find(b'\xff\xd8')
                jpeg_end = part.rfind(b'\xff\xd9')
                
                if jpeg_start != -1 and jpeg_end != -1:
                    jpg = part[jpeg_start:jpeg_end+2]
                    
                    try:
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            frame = cv2.resize(frame, (480, 360))
                            if frame_queue.full():
                                frame_queue.get()
                            frame_queue.put(frame)
                    except:
                        pass
                
                buffer = buffer[end:]
        else:
            # Fallback JPEG parsing
            a = buffer.find(b'\xff\xd8')
            b = buffer.find(b'\xff\xd9')
            
            if a != -1 and b != -1:
                jpg = buffer[a:b+2]
                buffer = buffer[b+2:]
                
                try:
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        frame = cv2.resize(frame, (480, 360))
                        if frame_queue.full():
                            frame_queue.get()
                        frame_queue.put(frame)
                except:
                    pass


# =========================
# LOAD KNOWN FACE
# =========================
img = cv2.imread("known.jpg")

if img is None:
    print("❌ Could not load 'known.jpg'")
    exit()

rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
encodings = face_recognition.face_encodings(rgb_img)

if len(encodings) == 0:
    print("❌ No face found in known.jpg")
    exit()

known_encoding = encodings[0]  # ✅ FIXED
print("✅ Reference face encoded")


# =========================
# START STREAM THREAD
# =========================
threading.Thread(target=read_stream, daemon=True).start()
print("✅ Stream started...")

# =========================
# MAIN LOOP
# =========================
frame_count = 0
last_unlock_time = 0

while True:
    try:
        frame = frame_queue.get(timeout=2)
    except:
        print("⚠️ No frames received")
        continue

    frame_count += 1

    # Resize for speed
    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
    rgb_frame = np.ascontiguousarray(rgb_frame)

    # Process every 3rd frame
    if frame_count % 3 == 0:
        face_locations = face_recognition.face_locations(rgb_frame, model="hog")
        # face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
        try:
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations, num_jitters=1)
        except Exception as e:
            print("❌ Encoding error:", e)
            continue
    else:
        continue

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        
        # Scale back up
        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        # ✅ DISTANCE-BASED MATCHING
        distance = face_recognition.face_distance([known_encoding], face_encoding)[0]
        is_match = distance < 0.45   # 🔐 strict threshold

        confidence = (1 - distance) * 100

        label = f"AUTHORIZED ✅ {confidence:.1f}%" if is_match else f"UNKNOWN ❌ {confidence:.1f}%"
        color = (0, 255, 0) if is_match else (0, 0, 255)

        # 🔓 Unlock with cooldown
        if is_match and (time.time() - last_unlock_time > 5):
            try:
                requests.get("http://10.98.104.222/action?go=on", timeout=1)
                print("🔓 Door Unlocked")
                last_unlock_time = time.time()
            except:
                print("❌ Unlock request failed")

        # Draw box
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, label, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("Face Unlock System", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        stop_flag = True
        break

cv2.destroyAllWindows()