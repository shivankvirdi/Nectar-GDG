import os
import clip
import torch
import requests
from io import BytesIO
import pytesseract
from PIL import Image, ImageGrab
import matplotlib.pyplot as plt

device = "cuda" if torch.cuda.is_available() else "cpu"
categories=[
    'laptop', 'smartphone', 'wired earbuds', 'wireless earbuds', 'headphones',
    'monitor', 'television', 'speaker', 'tablet', 'computer mouse', 'camera', 'keyboard',
    'printer', 'gaming console', 'charger', 'router', 'microphone', 'watch'
]

def load_model(model_name='ViT-B/32'):
    return clip.load(model_name, device=device)

def load_ocr_path():
    TESSERACT_PATH = r"C:\Users\shiva\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

    if not os.path.isfile(TESSERACT_PATH):
        print("ERROR: tesseract.exe not found at:")
        print(TESSERACT_PATH)

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

def load_image(src: str):
    try:
        if src.startswith(("http://", "https://")):
            response = requests.get(src, timeout=5)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
    except requests.exceptions.Timeout:
        print('The request timed out')

def classify(image, model, preprocess, categories):
    image_input = preprocess(image).unsqueeze(0).to(device)
    text_inputs = torch.cat([clip.tokenize(f"a photo of a {c}") for c in categories]).to(device)

    with torch.no_grad():
        image_features = model.encode_image(image_input)
        text_features = model.encode_text(text_inputs)

    image_features /= image_features.norm(dim=-1, keepdim=True)
    text_features /= text_features.norm(dim=-1, keepdim=True)
    similarity = (100.0 * image_features @ text_features.T).softmax(dim=-1)
    t_value, t_index = similarity[0].topk(1)

    return {'label': categories[t_index[0].item()], 'val': t_value[0].item()}

def ocr_cap(img):
    text = pytesseract.image_to_string(img)
    print(f"Model: {text}")

def run_model():
    load_ocr_path()
    model, preprocess = load_model()
    # you can input any image type consistent with the categories
    image = load_image('https://www.sellerapp.com/blog/wp-content/uploads/2022/05/amazon-product-detail-page-standards-1100x489.jpg')
    result = classify(image, model, preprocess, categories)

    plt.imshow(image)
    plt.axis('off')
    plt.show()

    print(f"Category: {result['label']:>16s}: {100 * result['val']:.2f}% match")
    ocr_cap(image)

if __name__ == '__main__':
    run_model()