# استخدام نسخة Node.js خفيفة ورسمية
FROM node:18-alpine AS base

# استقبال متغير البيئة من docker-compose (اختياري لكن مفضل)
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# تحديد مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ ملفات التعريف وتثبيت الاعتماديات
COPY package*.json ./
RUN npm ci

# نسخ باقي ملفات المشروع
COPY . .

# بناء المشروع (Build)
RUN npm run build

# فتح المنفذ 3000
EXPOSE 3000

# تشغيل المشروع
CMD ["npm", "start"]
