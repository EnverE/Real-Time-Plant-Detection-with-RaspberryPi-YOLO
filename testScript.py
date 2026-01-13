from ultralytics import YOLO

# Load your trained model
model = YOLO(r"dataPath\train\weights\best.pt")
source_folder = r"testData"

results = model.predict(
    source=source_folder,   # folder path
    imgsz=640,              # same image size as training
    conf=0.5,               # confidence threshold (adjust if needed)
    save=True,              # saves images with detections
    save_txt=True           # saves label files (optional)
)