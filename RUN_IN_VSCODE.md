# تشغيل المشروع في VS Code

## 1) افتح المجلد الصحيح
افتح مجلد `dep_pro` (أو جذر المستودع) في VS Code:
```bash
code dep_pro
```

## 2) ثبّت الإضافات المطلوبة
اضغط `Ctrl+Shift+X` وثبّت:
- **Python** (ms-python.python)
- **Ruff** (charliermarsh.ruff)
- **Python Debugger** (ms-python.debugpy)

## 3) جهّز البيئة الخلفية (Backend)
في الطرفية (`Ctrl+`` `):
```bash
cd dep_pro/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # أو cp -n .env.example .env على Linux/Mac
```
ثم عدّل `.env` وتأكد أن `DATABASE_URL` يشير إلى PostgreSQL يعمل على جهازك
(يمكن تشغيل قاعدة البيانات فقط عبر Docker):
```bash
docker run -d --name sdp-db -p 5432:5432 \
  -e POSTGRES_USER=sdp_user -e POSTGRES_PASSWORD=change-me-strong-password \
  -e POSTGRES_DB=sdp_db pgvector/pgvector:pg16

python -m scripts.init_db    # إنشاء الجداول
python -m scripts.seed_db    # (اختياري) بيانات تجريبية
```

## 4) جهّز الواجهة (Frontend)
```bash
cd ../frontend
npm install
```

## 5) التشغيل من داخل VS Code

### الطريقة أ — زر Run (موصى بها):
1. افتح تبويب **Run and Debug** (`Ctrl+Shift+D`).
2. اختر من القائمة:
   - **Full Stack: Backend + Frontend** لتشغيل الخادمين معًا، أو
   - **Backend: FastAPI (uvicorn)** لواجهة خلفية فقط (مع نقاط توقف/Debug).
3. اضغط `F5`.
   - الخلفية: http://localhost:8000 (التوثيق: http://localhost:8000/docs)
   - الواجهة: http://localhost:3000

### الطريقة ب — Tasks:
`Ctrl+Shift+P` → **Tasks: Run Task** ثم اختر مثل:
- `Backend: Install dependencies`
- `Backend: Init database`
- `Frontend: Dev server`
- `Backend: Run tests`

### الطريقة ج — الطرفية يدويًا:
```bash
# نافذة طرفية 1
cd dep_pro/backend && uvicorn app.main:app --reload --port 8000

# نافذة طرفية 2 (Split Terminal)
cd dep_pro/frontend && npm run dev
```

## 6) التشغيل الكامل عبر Docker (بديل)
```bash
cd dep_pro
cp .env.example .env   # وعدّل POSTGRES_PASSWORD و JWT_SECRET_KEY
docker compose up -d --build
```
ثم افتح http://localhost:8080

## ملاحظات
- إذا طلب VS Code اختيار مفسّر Python، اختر `dep_pro/backend/.venv`.
- اختصار فتح طرفيتين معًا: `Ctrl+Shift+5` ثم أيقونة Split في الطرفية.
- لإيقاف خادم يعمل في الطرفية: `Ctrl+C`.
