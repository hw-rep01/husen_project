class PlatformError(Exception):
    """الأساس لكل أخطاء المنصة المتوقعة. تُترجم إلى استجابات HTTP في main.py."""


class AccessDeniedError(PlatformError):
    """المستخدم لا يملك صلاحية الوصول للمورد."""


class NotFoundError(PlatformError):
    """المورد غير موجود."""


class BusinessRuleError(PlatformError):
    """الطلب يخالف قاعدة عمل (كويز مغلق، تقديم مكرر، إلخ)."""


class IngestionError(PlatformError):
    """فشل معالجة ملف الملزمة."""


class NotGroundedError(PlatformError):
    """لا توجد أدلة كافية في الملازم للإجابة أو التوليد."""


class LLMNotConfiguredError(PlatformError):
    """مزود النموذج غير مضبوط (مفتاح API مفقود)."""


class LLMOutputError(PlatformError):
    """مخرجات النموذج غير صالحة ولا يمكن استخدامها."""
