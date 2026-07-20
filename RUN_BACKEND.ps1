cd D:\PUSAKA\certificate_autofill_FIXED_UI\backend
D:\PUSAKA\certificate_autofill_prototype\okeenv\Scripts\activate
$env:APP_ENV="development"
$env:DATABASE_URL="postgresql+psycopg2://postgres:1111@127.0.0.1:5434/certautofill"
$env:PROCESSING_MODE="background"
$env:MAX_UPLOAD_SIZE_MB="10"
$env:MIN_TEXT_LENGTH="80"
$env:ENABLE_DOCLING="true"
$env:ENABLE_OCR_FALLBACK="true"
$env:MAX_JOB_RETRIES="3"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
