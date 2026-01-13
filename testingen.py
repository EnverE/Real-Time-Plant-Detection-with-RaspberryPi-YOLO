import cv2
cap = cv2.VideoCapture("udp://192.168.137.208:8000", cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
if not cap.isOpened(): exit()
while True:
    ret, frame = cap.read()
    if not ret: break
    cv2.imshow("Test 3: Low Bitrate (1 Mbps)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break
cap.release(); cv2.destroyAllWindows()