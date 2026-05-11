# <img src="public/opencr-logo.png" width="40" valign="middle"> OpenCR: Türkçe ve Karmaşık Dökümanlar İçin Yüksek Performanslı OCR Hattı

OpenCR, özellikle Türkçe metinler, arşiv dökümanları ve karmaşık sayfa yapısına sahip PDF'leri, yapay zeka eğitimine hazır (HuggingFace-ready) tertemiz veri setlerine dönüştüren uçtan uca bir sistemdir.

## Neden OpenCR?

- **Türkçe Odaklı Doğruluk:** DeepSeek-OCR-2 tabanlı yapısıyla, standart OCR araçlarının zorlandığı Türkçe karakterlerde ve karmaşık sayfa düzenlerinde güçlü bir başlangıç noktası sağlar.
- **Veri Seti Fabrikası:** Çıkarılan metinleri doğrudan `.parquet` formatında paketler ve tek tıkla HuggingFace'e yüklemeye hazır hale getirir.
- **Operatör Konsolu:** İşlemleri izlemek, sayfa sayfa kontrol etmek ve hataları düzeltmek için modern bir web arayüzü sunar.

## Kurulum

### Docker ile Çalıştırma (NVIDIA GPU Gerekir)
```bash
docker compose up -d
```

### Harici Model Sunucusu ile Geliştirme
Zaten çalışan OpenAI-compatible bir vLLM / GPU endpoint'iniz varsa:

1. **Klasör ve Ortam Hazırlığı:**
   ```bash
   mkdir -p input output
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r ocr_pipeline/requirements.txt
   ```

2. **Başlatma:**
   ```bash
   export INPUT_DIR="./input"
   export OUTPUT_DIR="./output"
   MODEL_BACKEND=remote MODEL_SERVER_URL="https://your-endpoint" ./scripts/start.sh
   ```
   Erişim: **http://localhost:39672**

## Mimari
- **Backend:** vLLM tabanlı DeepSeek-OCR-2 (GPU-first).
- **Frontend/API:** FastAPI & Alpine.js (Yönetim konsolu).

---
*OpenCR, döküman arşivlerini dijitalleştirip modern yapay zeka dünyasına taşımak için [cdli.ai](https://cdli.ai) tarafından geliştirilmiştir.*
