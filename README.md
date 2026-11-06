# husen_project
project for collage mangment sestem with ai models 
# 🎓 نظام إدارة الكلية المدعوم بالذكاء الاصطناعي (AI College Management System)

منصة متكاملة وحديثة لإدارة العمليات الأكاديمية والإدارية في الكليات، مدعومة بنماذج ذكاء اصطناعي (AI Models) لأتمتة المهام، تحسين تجربة المستخدم، وتقديم رؤى ذكية.

---

## 🚀 الميزات الرئيسية

- 🤖 **دمج الذكاء الاصطناعي**: نماذج AI للمساعدة في الإجابات الذكية، تحليل البيانات، أو أتمتة العمليات (RAG/Chatbot).
- 📊 **لوحة تحكم شاملة**: واجهة مستخدم حديثة وسريعة مبنية بـ Next.js لإدارة الطلاب، الموظفين، والجداول الدراسية.
- 🔒 **أمان عالي**: نظام مصادقة آمن (JWT)، صلاحيات مستخدمين متعددة الأدوار (RBAC)، وحماية البيانات.
- 🐳 **جاهز للإنتاج (Production-Ready)**: بنية تحتية مبنية بالكامل على Docker و Docker Compose لتسهيل النشر والتطوير.
- 🧪 **اختبارات موثوقة**: يشمل اختبارات End-to-End (E2E) لضمان استقرار النظام.

---

## 🛠️ تقنيات المشروع (Tech Stack)

| المجال | التقنيات المستخدمة |
|--------|---------------------|
| **Frontend** | Next.js, TypeScript, Tailwind CSS, React |
| **Backend** | Python, FastAPI, SQLAlchemy, Pydantic |
| **Database** | PostgreSQL (أو قاعدة البيانات المستخدمة) |
| **AI / ML** | LangChain, OpenAI API / Local Models (حسب التطبيق) |
| **DevOps** | Docker, Docker Compose, GitHub Actions (قريباً) |
| **Testing** | Playwright / Cypress (E2E), Pytest |

---

## 📂 هيكل المشروع (Project Structure)

```text
dep_pro/
├── backend/          # واجهة برمجة التطبيقات (FastAPI) ومنطق الذكاء الاصطناعي
├── frontend/         # واجهة المستخدم (Next.js + TypeScript)
├── deploy/           # إعدادات النشر والـ CI/CD
├── e2e/              # اختبارات End-to-End
├── docker-compose.yml # إعدادات تشغيل الحاويات
├── .env.example      # مثال على متغيرات البيئة
└── README.md         # هذا الملف
