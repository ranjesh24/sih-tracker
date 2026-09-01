from ultralytics import YOLO

model = YOLO('yolov8s.pt')  # "small" instead of "nano" — still fast, notably more accurate

# Run detection on all 4 images in your reid_test folder
results = model.predict(
    source='sample_data/reid_test',
    save=True,
    conf=0.25,   # lowered from 0.4
    classes=[2, 3, 5, 7]
)

print("Done! Check the 'runs/detect/predict' folder for output images.")