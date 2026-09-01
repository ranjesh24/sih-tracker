import easyocr

reader = easyocr.Reader(['en'])

images = [
    'sample_data/reid_test/car_a_cam1.jpg',
    'sample_data/reid_test/car_a_cam2.jpg',
    'sample_data/reid_test/car_a_cam3.jpg',
    'sample_data/reid_test/car_b_cam1.jpg',
]

for img_path in images:
    print(f"\n--- {img_path} ---")
    results = reader.readtext(img_path)
    if results:
        for (bbox, text, confidence) in results:
            print(f"Detected text: {text} (confidence: {confidence:.2f})")
    else:
        print("No text detected")