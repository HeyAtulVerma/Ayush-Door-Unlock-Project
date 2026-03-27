import cv2
import face_recognition
import numpy as np
import requests
import threading
import time
import os
from queue import Queue

# =========================
# CONFIG
# =========================
KNOWN_DIR = "known"
UNLOCK_URL = "http://10.98.104.222/action?go=on"
THRESHOLD = 0.45

os.makedirs(KNOWN_DIR, exist_ok=True)

# =========================
# GLOBALS
# =========================
frame_queue = Queue(maxsize=5)
stop_flag = False

known_encodings = []
known_names = []

# =========================
# LOAD ALL KNOWN FACES
# =========================
def load_known_faces():
    global known_encodings, known_names
    
    known_encodings.clear()
    known_names.clear()
    
    for file in os.listdir(KNOWN_DIR):
        path = os.path.join(KNOWN_DIR, file)
        
        img = cv2.imread(path)
        if img is None:
            continue
        
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)
        
        enc = face_recognition.face_encodings(rgb)
        
        if len(enc) > 0:
            known_encodings.append(enc[0])
            known_names.append(file)
    
    print(f"✅ Loaded {len(known_encodings)} known faces")

# =========================
# SAVE NEW FACE
# =========================
def save_new_face(frame, face_location):
    top, right, bottom, left = face_location
    
    face_img = frame[top:bottom, left:right]
    
    filename = f"{KNOWN_DIR}/person_{int(time.time())}.jpg"
    cv2.imwrite(filename, face_img)
    
    print(f"📸 Saved new face: {filename}")
    
    load_known_faces()

# =========================
# STREAM THREAD (same as yours)
# =========================
def read_stream():
    global stop_flag
    stream_url = "http://10.98.104.43/stream"
    
    try:
        stream = requests.get(stream_url, stream=True, timeout=5)
        print("✅ Stream connected:", stream.status_code)
    except Exception as e:
        print("❌ Stream error:", e)
        return
    
    boundary = None
    buffer = b""
    
    for chunk in stream.iter_content(chunk_size=4096):
        if stop_flag:
            break
        
        buffer += chunk
        
        if boundary is None and 'boundary=' in stream.headers.get('Content-Type', ''):
            boundary = stream.headers['Content-Type'].split('boundary=')[-1].encode()
        
        if boundary:
            while True:
                start = buffer.find(b'--' + boundary)
                end = buffer.find(b'--' + boundary, start + 1)
                
                if start == -1 or end == -1:
                    break
                
                part = buffer[start:end]
                
                a = part.find(b'\xff\xd8')
                b = part.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = part[a:b+2]
                    
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), 1)
                    
                    if frame is not None:
                        frame = cv2.resize(frame, (480, 360))
                        
                        if frame_queue.full():
                            frame_queue.get()
                        
                        frame_queue.put(frame)
                
                buffer = buffer[end:]

# =========================
# INIT
# =========================
load_known_faces()

threading.Thread(target=read_stream, daemon=True).start()

last_unlock = 0
frame_count = 0

# =========================
# MAIN LOOP
# =========================
while True:
    try:
        frame = frame_queue.get(timeout=2)
    except:
        continue

    frame_count += 1
    
    small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)

    if frame_count % 3 != 0:
        cv2.imshow("System", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_flag = True
            break
        continue

    face_locations = face_recognition.face_locations(rgb)
    face_encodings = face_recognition.face_encodings(rgb, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        
        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        name = "UNKNOWN"
        color = (0, 0, 255)

        if len(known_encodings) > 0:
            distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match = np.argmin(distances)
            
            if distances[best_match] < THRESHOLD:
                name = known_names[best_match]
                color = (0, 255, 0)

                # Unlock
                if time.time() - last_unlock > 5:
                    try:
                        requests.get(UNLOCK_URL, timeout=1)
                        print(f"🔓 Unlocked for {name}")
                        last_unlock = time.time()
                    except:
                        print("❌ Unlock failed")

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, name, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("System", frame)

    key = cv2.waitKey(1) & 0xFF

    # =========================
    # PRESS 'i' TO REGISTER FACE
    # =========================
    if key == ord('i'):
        if len(face_locations) > 0:
            save_new_face(frame, (top, right, bottom, left))
        else:
            print("⚠️ No face to capture")

    elif key == ord('q'):
        stop_flag = True
        break

cv2.destroyAllWindows()