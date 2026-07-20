# Frontend sudah disertakan

Project ini punya dua cara menjalankan frontend:

## 1. Lewat backend FastAPI
Jalankan backend:

```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Buka:

```text
http://localhost:8000
```

## 2. Lewat folder frontend standalone
Jalankan static server:

```powershell
cd frontend
python -m http.server 5173
```

Buka:

```text
http://localhost:5173
```

Frontend standalone akan memanggil backend di `http://localhost:8000`.
