# 🐳 التشغيل عبر Docker (الطريقة الموصى بها)

المشروع الآن **جاهز للتشغيل على Docker** مع مفتاح الذكاء الاصطناعي (OpenAI) مضبوطاً تلقائياً.

## المتطلبات
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) أو Docker Engine + Compose plugin (Linux).

## خطوات التشغيل (3 أوامر فقط)

من مجلد `dep_pro`:

```bash
# 1) بناء الصور وتشغيل كل الخدمات (قاعدة بيانات + Redis + API + Worker + الواجهة)
docker compose up -d --build

# 2) انتظر دقيقة ثم تحقق من الحالة
docker compose ps

# 3) افتح التطبيق في المتصفح
#    http://localhost:8080
```

لإيقاف كل شيء:

```bash
docker compose down          # إيقاف مع الاحتفاظ بالبيانات
docker compose down -v       # إيقاف وحذف قاعدة البيانات بالكامل (للبداية من الصفر)
```

## ما تم ضبطه مسبقاً في ملف `.env`
| المتغير | القيمة | ملاحظة |
|---|---|---|
| `OPENAI_API_KEY` | ✅ مضبوط بالمفتاح الذي زوّدتنا به | يُستخدم للتوليد (LLM) وللتضمينات (Embeddings) |
| `EMBEDDING_PROVIDER` | `openai` | نموذج `text-embedding-3-small` |
| `EMBEDDING_DIMENSION` | `1536` | ⚠️ مفاتيح `sk-proj` الجديدة **لا تدعم** أبعاد التضمين المخصصة، لذا البُعد هو 1536 وليس 384 |
| `SEED_DEMO` | `true` | يملأ قاعدة البيانات ببيانات تجريبية عند أول تشغيل |
| `HTTP_PORT` | `8080` | منفذ الدخول عبر nginx (API + الواجهة معاً) |

## الخدمات التي تعمل
| الخدمة | الوصف |
|---|---|
| `db` | PostgreSQL + امتداد pgvector (لتخزين المتجهات) |
| `redis` | وسيط المهام الخلفية (Celery) |
| `migrate` | ينشئ الجداول ويملئ البيانات التجريبية ثم يتوقف |
| `api` | FastAPI — الوثائق: http://localhost:8080/api/docs |
| `worker` / `beat` | مهام Celery الخلفية والجدولة |
| `web` | واجهة Next.js |
| `proxy` | nginx — المدخل الوحيد: http://localhost:8080 |

## التحقق السريع
```bash
curl http://localhost:8080/health        # يجب أن يرجع {"status":"ok"} أو مشابه
docker compose logs -f api               # متابعة سجلات الـ API
```

## مشاكل شائعة
1. **خطأ بُعد التضمينات** — لا تغيّر `EMBEDDING_DIMENSION`؛ مفاتيح `sk-proj` تعيد 1536 دائماً. إذا غيّرتها يجب حذف الحجوم بـ `docker compose down -v` وإعادة التشغيل.
2. **MIME type / خطأ بناء الواجهة** — احذف `frontend/node_modules` محلياً ليس مهماً؛ البناء يتم داخل الحاوية. أعد المحاولة بـ `docker compose build --no-cache web`.
3. **منفذ 8080 محجوز** — غيّر `HTTP_PORT` في `.env` ثم `docker compose up -d proxy`.
4. **المفتاح غير صالح / رصيد منتهٍ** — ستظهر رسالة `OPENAI_API_KEY غير مضبوط` أو خطأ 401 من OpenAI في `docker compose logs worker api`. استبدل المفتاح في `.env` وأعد: `docker compose up -d`.

## 🔒 ملاحظة أمنية مهمة
مفتاح OpenAI محفوظ في ملف `.env` وهو **مستثنى من Git** (موجود في `.gitignore`) ولن يُرفع للموقع. لكن بما أنك شاركته في المحادثة، يُنصح بشدة بـ:
- فتح منصة OpenAI → API keys → **Revoke** لهذا المفتاح وإنشاء جديد.
- تحديثه في `.env` ثم `docker compose up -d`.
