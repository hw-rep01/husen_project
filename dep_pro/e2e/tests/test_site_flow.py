"""
اختبارات المتصفح الحقيقية: تشغّل الواجهة والخلفية وتجرب الموقع كما يفعل المستخدم.

التشغيل (مع تشغيل الخلفية على 8000 والواجهة على 3000):
    E2E_BASE_URL=http://localhost:3000 pytest e2e/tests -q
واختيارياً مسار المتصفح إن لم يكن Playwright قد نزّل متصفحه:
    E2E_CHROMIUM_PATH=/usr/bin/chromium
"""

import os
import re
import time
import uuid

import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:3000")
PASSWORD = "ChangeMe123!"


@pytest.fixture(scope="module")
def browser():
    launch_args = {"headless": True}
    if os.environ.get("E2E_CHROMIUM_PATH"):
        launch_args["executable_path"] = os.environ["E2E_CHROMIUM_PATH"]
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_args)
        yield browser
        browser.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    yield ctx
    ctx.close()


def login(page: Page, email: str) -> None:
    page.goto(f"{BASE_URL}/login")
    page.get_by_label("البريد الإلكتروني").fill(email)
    page.get_by_label("كلمة المرور").fill(PASSWORD)
    page.get_by_role("button", name="تسجيل الدخول").click()
    expect(page).to_have_url(re.compile(r"/home$"), timeout=15000)


def logout(page: Page) -> None:
    page.get_by_role("button", name="خروج").click()
    expect(page).to_have_url(re.compile(r"/login$"))


def card_for(page: Page, title: str):
    return page.locator("article, li").filter(has_text=title).first


# ---------- الدخول والتنقل ----------

def test_guest_is_redirected_to_login(context):
    page = context.new_page()
    page.goto(f"{BASE_URL}/home")
    expect(page).to_have_url(re.compile(r"/login$"))


def test_wrong_password_shows_error(context):
    page = context.new_page()
    page.goto(f"{BASE_URL}/login")
    page.get_by_label("البريد الإلكتروني").fill("student@sdp.local")
    page.get_by_label("كلمة المرور").fill("wrong-password")
    page.get_by_role("button", name="تسجيل الدخول").click()
    # الرسالة في عنصر الخطأ نفسه، وليس في منطقة إعلانات Next.js المخفية
    expect(page.locator('p[role="alert"]')).to_contain_text("بيانات الدخول غير صحيحة")


def test_student_home_shows_course_and_navigation(context):
    page = context.new_page()
    login(page, "student@sdp.local")
    expect(page.get_by_text("طالب تجريبي").first).to_be_visible()
    expect(page.get_by_role("link", name="طلباتي")).to_be_visible()
    expect(page.get_by_role("link", name="الجدول")).to_be_visible()
    expect(page.get_by_role("link", name="التبليغات")).to_be_visible()
    expect(page.get_by_role("link", name="هندسة المتطلبات")).to_be_visible()


def test_course_page_has_assistant_and_quiz_tabs(context):
    page = context.new_page()
    login(page, "student@sdp.local")
    page.get_by_role("link", name="هندسة المتطلبات").click()
    expect(page.get_by_role("heading", name="هندسة المتطلبات")).to_be_visible()
    expect(page.get_by_role("button", name="المساعد الذكي")).to_be_visible()
    expect(page.get_by_role("button", name="الكويزات")).to_be_visible()
    # إدارة المادة للدكتور فقط
    expect(page.get_by_role("button", name="إدارة المادة")).to_have_count(0)


def test_instructor_sees_staff_tab(context):
    page = context.new_page()
    login(page, "dr@sdp.local")
    page.get_by_role("link", name="موادي").click()
    page.get_by_role("link", name="هندسة المتطلبات").click()
    expect(page.get_by_role("button", name="إدارة المادة")).to_be_visible()


# ---------- الطلب كاملاً عبر الأدوار ----------

def test_full_administrative_request_flow_across_roles(browser):
    """الطالب يرسل ← ممثل الشعبة يصنّف ويحيل ← مقرر القسم يحيل ← رئيس القسم يوافق ← الطالب يرى القرار."""
    subject = f"مشكلة القاعة {uuid.uuid4().hex[:6]}"
    body = "القاعة مغلقة صباحاً ونحتاج فتحها قبل المحاضرة الأولى"

    student_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    student = student_ctx.new_page()
    login(student, "student@sdp.local")
    student.goto(f"{BASE_URL}/requests")
    student.get_by_label("عنوان الطلب", exact=True).fill(subject)
    student.get_by_label("التفاصيل", exact=True).fill(body)
    student.get_by_role("button", name="إرسال", exact=True).click()
    expect(student.get_by_text("تم إرسال طلبك إلى ممثل شعبتك.")).to_be_visible()
    expect(student.get_by_text(subject, exact=True)).to_be_visible()
    student_ctx.close()

    rep_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    rep = rep_ctx.new_page()
    login(rep, "rep@sdp.local")
    rep.goto(f"{BASE_URL}/requests")
    rep_card = card_for(rep, subject)
    expect(rep_card).to_be_visible()
    rep_card.get_by_role("button", name="إداري", exact=True).click()
    rep_card.get_by_role("button", name="إحالة للجهة التالية").click()
    # الطلب يبقى في قائمة الشعبة للعرض، لكن المرحلة تنتقل إلى مقرر القسم ولا تُعرض الإحالة مجدداً
    expect(rep_card.get_by_text("مقرر القسم").first).to_be_visible(timeout=10000)
    expect(rep_card.get_by_role("button", name="إحالة للجهة التالية")).to_have_count(0)
    rep_ctx.close()

    coord_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    coord = coord_ctx.new_page()
    login(coord, "coord@sdp.local")
    coord.goto(f"{BASE_URL}/requests")
    coord_card = card_for(coord, subject)
    expect(coord_card).to_be_visible()
    coord_card.get_by_role("button", name="إحالة للجهة التالية").click()
    expect(coord.get_by_text(subject, exact=True)).to_have_count(0, timeout=10000)
    coord_ctx.close()

    head_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    head = head_ctx.new_page()
    login(head, "head@sdp.local")
    head.goto(f"{BASE_URL}/requests")
    head_card = card_for(head, subject)
    expect(head_card).to_be_visible()
    head_card.get_by_role("button", name="موافقة", exact=True).click()
    expect(head_card.get_by_text("موافقة", exact=True).first).to_be_visible(timeout=10000)
    head_ctx.close()

    student_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    student = student_ctx.new_page()
    login(student, "student@sdp.local")
    student.goto(f"{BASE_URL}/requests")
    student_row = card_for(student, subject)
    expect(student_row.get_by_text("موافقة", exact=True)).to_be_visible()
    student_row.get_by_role("button", name="عرض السجل الزمني").click()
    expect(student_row.get_by_text("تم تقديم الطلب")).to_be_visible()
    student_ctx.close()


def test_two_tabs_with_different_accounts_do_not_break_each_other(browser):
    """
    انحدار للخلل الذي ظهر سابقاً: التبويبات كانت تتشارك localStorage، فيستبدل تسجيل
    حساب في تبويب رمز الحساب في تبويب آخر، فتظهر أخطاء 403 غير مفهومة.
    الآن كل تبويب يحتفظ بجلسته (sessionStorage)، فالتبويبان يعملان معاً.
    """
    ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    rep_tab = ctx.new_page()
    login(rep_tab, "rep@sdp.local")

    coord_tab = ctx.new_page()
    login(coord_tab, "coord@sdp.local")

    rep_tab.bring_to_front()
    rep_tab.goto(f"{BASE_URL}/requests")
    expect(rep_tab.get_by_role("heading", name="طلبات الشعبة")).to_be_visible()
    expect(rep_tab.get_by_text("ليست لديك صلاحية")).to_have_count(0)
    ctx.close()


def test_representative_cannot_see_forbidden_actions_for_student(browser):
    ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    page = ctx.new_page()
    login(page, "student@sdp.local")
    page.goto(f"{BASE_URL}/requests")
    expect(page.get_by_role("heading", name="طلب جديد")).to_be_visible()
    expect(page.get_by_role("button", name="إحالة للجهة التالية")).to_have_count(0)
    ctx.close()


# ---------- التبليغات ----------

def test_broadcast_publish_read_and_readers_list(browser):
    title = f"تعميم {uuid.uuid4().hex[:6]}"

    coord_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    coord = coord_ctx.new_page()
    login(coord, "coord@sdp.local")
    coord.goto(f"{BASE_URL}/broadcasts")
    coord.get_by_label("العنوان", exact=True).fill(title)
    coord.get_by_label("نص التبليغ", exact=True).fill("يرجى مراجعة الجدول الجديد قبل بداية الأسبوع")
    coord.get_by_role("button", name="نشر", exact=True).click()
    expect(coord.get_by_text("تم نشر التبليغ وإشعار المستهدفين.")).to_be_visible()
    coord_ctx.close()

    student_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    student = student_ctx.new_page()
    login(student, "student@sdp.local")
    student.goto(f"{BASE_URL}/broadcasts")
    row = card_for(student, title)
    expect(row).to_be_visible()
    row.get_by_role("button", name="تم الاطلاع").click()
    expect(row.get_by_text("تم الاطلاع", exact=True)).to_be_visible()
    student_ctx.close()

    coord_ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    coord = coord_ctx.new_page()
    login(coord, "coord@sdp.local")
    coord.goto(f"{BASE_URL}/broadcasts")
    row = card_for(coord, title)
    expect(row.get_by_text(re.compile(r"قرأه 1 من"))).to_be_visible()
    row.get_by_role("button", name="من قرأ؟").click()
    expect(row.get_by_text("طالب تجريبي")).to_be_visible()
    coord_ctx.close()


def test_student_cannot_publish_department_broadcast(browser):
    ctx = browser.new_context(locale="ar-IQ", timezone_id="Asia/Baghdad")
    page = ctx.new_page()
    login(page, "student@sdp.local")
    page.goto(f"{BASE_URL}/broadcasts")
    expect(page.get_by_role("button", name="نشر", exact=True)).to_have_count(0)
    ctx.close()


# ---------- الجدول الحي ----------

def test_schedule_page_connects_to_live_stream(context):
    page = context.new_page()
    login(page, "student@sdp.local")
    page.goto(f"{BASE_URL}/schedule")
    expect(page.get_by_role("heading", name="الجدول الأسبوعي")).to_be_visible()
    expect(page.get_by_text("مباشر")).to_be_visible(timeout=15000)


def test_logout_clears_session_and_blocks_pages(context):
    page = context.new_page()
    login(page, "student@sdp.local")
    logout(page)
    page.goto(f"{BASE_URL}/requests")
    expect(page).to_have_url(re.compile(r"/login$"))
