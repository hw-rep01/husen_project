# استخدام نسخة Node.js خفيفة
FROM node:18-alpine

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملفات التعريف وتثبيت الاعتماديات
COPY package*.json ./
RUN npm install

# نسخ باقي ملفات المشروع
COPY . .

# بناء المشروع (Build)
RUN npm run build

# فتح المنفذ 3000
EXPOSE 3000

# تشغيل المشروع
CMD ["npm", "start"]
