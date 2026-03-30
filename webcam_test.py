#If you would like to test the model without your pi you can use this one
from ultralytics import YOLO
model = YOLO('dataPath/train/weights/best2.pt')
model.predict(
    source=0,
    show=True,
    conf=0.6,
    imgsz=640
)