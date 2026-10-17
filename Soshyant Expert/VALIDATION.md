# بررسی نسخه محلی

## موارد انجام‌شده

- اجرای مستقل Python از پوشه runtime و واردکردن وابستگی‌ها بدون محیط پروژه قبلی.
- بررسی صحت دارایی‌ها با SHA-256 و اجرای واقعی مدل جست‌وجوی محلی با خروجی ۳۸۴بعدی.
- ۷۰ آزمون خودکار موفق: جداسازی گفت‌وگو، نقش‌ها، CSRF، محدودیت مبدا و Host، نشست و خروج، آرشیو، نسخه سند، دانلود نسخه تاریخی، قطع پردازش، عدم انتشار ناقص، رد ارجاع نامعتبر، پشتیبان‌گیری و بازیابی.
- اجرای مدل واقعی Bonsai روی سند ساختگی موقت: پاسخ صحیح به مدت و مدارک گارانتی، همراه شاهد؛ سپس پاسخ فارسی صحیح به پرسش دنباله‌دار. نتیجه در VALIDATION-real.json است.
- در آزمون مدل واقعی، اتصال‌های socket پایتون فقط به loopback مجاز بودند. این آزمون نظارت کامل بر ترافیک پردازش‌های بومی یا تأیید جداسازی شبکه سیستم‌عامل نیست.
- بررسی رابط با مرورگر روی داده آزمایشی جدا: ورود، ارسال سؤال، نمایش پاسخ، بازکردن شاهد، ثبت بازخورد، کتابخانه و تنظیم تخصص.
- نسخه اصلی برای راه‌اندازی اولیه بدون حساب پیش‌فرض و بدون ورود خودکار سند نمونه باقی مانده است.

## موارد تأییدنشده

- نصب روی یک دستگاه تمیز دیگر و آزمون قطع فیزیکی شبکه یا ثبت کامل ترافیک سیستم‌عامل.
- کیفیت تخصصی روی دامنه واقعی مشتری، مجموعه ۱۰۰ تا ۲۰۰ پرسش مرجع و زبان‌های مورد نیاز مشتری.
- ظرفیت کاربران هم‌زمان و زمان پاسخ در حجم سند واقعی؛ مدل فعلاً یک پاسخ را در هر لحظه پردازش می‌کند و بقیه در صف محدود منتظر می‌مانند.
- استقرار شبکه داخلی با گواهی TLS مجموعه، سیاست فایل‌ها، بررسی امنیت مستقل و پذیرش عملیاتی.
- مجوزهای متفاوت برای تک‌تک اسناد؛ این نسخه دانش مشترک یک سازمان دارد. (OCR انگلیسی اکنون افزوده شده است؛ بخش «OCR انگلیسی» در پایین.)

این نتایج، آماده‌بودن یک نسخه محلی برای پایلوت را نشان می‌دهند؛ ادعای تأیید تخصص یا آمادگی قطعی تولید نیستند.

## انتخاب زبان

پیش‌فرض رابط و پاسخ API انگلیسی است. گزینه English / فارسی در ورود و محیط اصلی قرار دارد، انتخاب در مرورگر ذخیره می‌شود و تغییر جهت نمایش متن پرسش در حال نوشتن را حفظ می‌کند. پاسخ‌های قبلی و متن منابع ترجمه نمی‌شوند. انتخاب زبان برای پرسش‌های جدید ارسال می‌شود. آزمون واقعی روی سؤال فارسی با انتخاب انگلیسی، پاسخ انگلیسی همراه ارجاع تولید کرد. کنترل تشخیص خط خروجی و یک نوبت اصلاح، از انتشار خروجی آشکارا با خط نادرست جلوگیری می‌کند؛ این کنترل جای ارزیابی کامل کیفیت زبان را نمی‌گیرد.


## ماشین‌حساب سخت‌افزار

شش آزمون محاسبات ظرفیت و یک آزمون API اضافه شد؛ مجموع ۴۷ آزمون موفق است. فرمول KV، مدل ترکیبی، تغییر تعداد کاربران و ظرفیت متن، قالب وزن، ناکافی‌بودن حافظه هر کارت، اعتبارسنجی ورودی و جداسازی آزمون سرعت مدل‌ها بررسی شدند. رابط روی داده موقت با ۱۰۰ کاربر، تغییر مدل، هشدار عدم جاگیری و جابه‌جایی انگلیسی/فارسی با حفظ ورودی‌ها بررسی شد. این‌ها صحت منطق برآورد را بررسی می‌کنند؛ آزمون بار واقعی روی سخت‌افزار پیشنهادی انجام نشده است.


## مدل فعال و ورود پوشه

مجموع نهایی ۵۴ آزمون خودکار موفق است. ثبت GGUF محلی، حفظ انتخاب پس از راه‌اندازی مجدد، جلوگیری از تغییر مدل حین پاسخ‌های در انتظار و جلوگیری از پرسش جدید هنگام فعال‌سازی، بازگشت تنظیمات پس از خطا و دسترسی صرفاً مدیر بررسی شدند. آزمون واقعی با تنظیمات موقت، مدل همراه را بارگذاری کرد؛ سپس شکست فعال‌سازی یک مدل خراب و بارگذاری مجدد مدل قبلی با موفقیت بررسی شد.

در مرورگر و روی داده آزمایشی، پوشه‌ای با چهار فایل انتخاب شد: دو سند، شامل یک سند داخل زیرپوشه، نمایه شد؛ یک فایل تکراری و یک نوع پشتیبانی‌نشده رد شدند. هیچ سند آزمایشی به داده واقعی اضافه نشد. منوی انتخاب مدل و بخش ورود پوشه در نسخه اصلی ارائه شده‌اند. سازگاری و کیفیت مدل‌های دیگری که هنوز تهیه نشده‌اند تأیید نشده است.


## حذف سند بایگانی‌شده و مدل خارج از پوشه برنامه

مجموع نهایی ۵۷ آزمون موفق است. حذف فقط برای سند بایگانی‌شده، مدیر، CSRF معتبر و تأیید صریح مجاز است؛ پاک‌شدن نسخه‌های فایل و قطعات نمایه و جلوگیری از بازگردانی سند حذف‌شده بررسی شد. پنجره تأیید و مسیر انصراف در مرورگر روی داده موقت بررسی شدند؛ هیچ سند واقعی حذف نشد. آزمون ثبت و فعال‌سازی فایل مدل از پوشه‌ای خارج از ریشه برنامه نیز موفق بود و نشان داد فایل بدون کپی در مسیر اصلی خود می‌ماند.


## انتخاب مدل با پوشه در یک پنل

۶۰ آزمون خودکار موفق شدند. انتخاب پوشه، شناسایی بازگشتی و غیر‌بازگشتی GGUF، رد فایل نامعتبر، حفظ پوشه پس از راه‌اندازی مجدد و محدودیت دسترسی مدیر بررسی شدند. در مرورگر، خطای مسیر نامعتبر به‌وضوح نمایش داده شد، پوشه واقعی مدل اسکن شد و مدل در منو قرار گرفت؛ انتخاب پوشه از درایو محلی، ورود به زیرپوشه و برگشت، انتخاب پوشه و جابه‌جایی زبان با حفظ مسیر نیز بررسی شدند. دو بخش قبلی با یک پنل واحد جایگزین شدند.


## مدل API اختیاری

مجموعه کامل ۶۸ آزمون موفق بود و سپس یک آزمون جدا برای برگشت از مدل API به مدل محلی نیز موفق شد. حفاظت واقعی DPAPI در ویندوز، عدم بازگشت کلید در پاسخ API، قالب درخواست OpenAI و سرویس سازگار، تأیید ارسال اطلاعات، بازگشت انتخاب پس از خطا، رد پرسش از صفحه دارای انتخاب قدیمی، خطاهای بدون افشای کلید، پاسخ ناقص، لغو و پاسخ مستند در مسیر HTTP/Engine با ارائه‌دهنده شبیه‌سازی‌شده بررسی شدند. در مرورگر، ذخیره اتصال با کلید ساختگی، اضافه‌شدن به منوی مدل‌ها، خالی‌شدن فیلد کلید، منع فعال‌سازی بدون تأیید و تغییر زبان بررسی شدند. هیچ حساب واقعی OpenAI یا ارائه‌دهنده دیگری فراخوانی نشده است؛ پذیرش با کلید واقعی و مدل در دسترس مشتری هنوز نیازمند آزمون هنگام فعال‌سازی است.


## برنامه اندروید و دسترسی وای‌فای

مجموعه کامل ۷۰ آزمون سرور موفق شد؛ بودجه تلاش ناموفق ورود اکنون با ورودهای موفق متعدد پشت درگاه مشترک مصرف نمی‌شود. APK برنامه بومی با SDK رسمی ساخته شد و امضاهای v2/v3 آن تأیید شدند. همان کد Java حمل‌ونقل داخل APK، مقابل یک درگاه HTTPS واقعی و داده موقت، گواهی CA، رد گواهی نامعتبر یا نام میزبان نادرست، نشست امن، CSRF، پرسش و پیگیری، شاهد، تاریخچه و خروج را با موفقیت بررسی کرد. محدودیت Host/Origin و بسته‌بودن مسیرهای مدیریتی هم بررسی شد.

درگاه واقعی روی رابط وای‌فای فعلی اجرا و سلامت HTTPS آن از همین کامپیوتر تأیید شد. داده واقعی برای پرسش آزمایشی یا حساب نمونه استفاده نشد؛ گواهی عمومی و راهنمای اتصال در پوشه dist پروژه اندروید است. نصب روی گوشی واقعی، رابط روی اندروید/شبیه‌ساز و دسترسی از یک دستگاه دیگر وای‌فای هنوز بررسی نشده است.


## Android 1.1 chat experience — 2026-10-17

The complete server suite passed 72 tests. The new checks cover ownership, CSRF, strict deletion confirmation, title validation, pending-answer protection, refusal to submit to a deleted conversation, and removal of messages/feedback/saved answer-job copies while preserving other chats. The exact Java API transport passed the real HTTPS gateway integration test for rename, feedback and confirmed deletion, in addition to login, asks, citations, TLS trust and gateway restrictions. Tests use temporary data only.

The 1.1 APK compiles with the existing pilot signing identity and passes v2/v3 signature verification. Native UI additions include searchable chat titles, chat options, timestamps, basic answer formatting, copy/share, UTF-8 text export and feedback notes. The user reported that 1.0 worked on their phone; the new 1.1 UI still needs physical-phone acceptance testing. Restart both the main server and Wi-Fi gateway before using the updated APK. No real user conversation was deleted during development.


## Windows usability milestone — 2026-10-17

All 74 automated tests passed, including isolated hidden-host start/stop and administrator dashboard ownership/count checks. C# launcher compiled successfully and its native window correctly detected the already-running external server without taking control of it. Browser checks on disposable data verified overview statistics, English/Persian rendering, responsive layout, chat rename/title search, the deletion confirmation dialog, and a completed cited answer with rename/delete controls re-enabled afterward. Deletion itself is covered by automated API tests; no production data was deleted. The existing real model selection and configuration were preserved. See DESKTOP.md for the remaining roadmap and pilot limitations.


## Watched folders and answer review — 2026-10-17

The full suite passed 83 tests. The Android Java HTTPS integration test also passed against the updated server. Additional targeted checks passed after final changes to the feedback/review transaction and atomic creation of document staging/recovery records.

Workflow checks cover scan-only discovery, stable fingerprints and stale approvals, local path boundaries, incomplete scans, missing-file archive confirmation, preservation of published content after failed or canceled indexing, hidden staging documents, replacement at the logical passage limit, revision retention, owner chat deletion cleanup, review status/filter validation, role/CSRF boundaries, pagination, and new feedback reopening resolved reviews.

In a disposable browser workspace, approved-file indexing and publication succeeded; the sidebar count updated afterward. The server folder browser, English/Persian controls, saved resolution notes, resolved filtering and preservation of draft notes across language changes were verified. No production accounts, watched paths, documents, chats, model settings or provider credentials were modified. See WATCHED-AND-REVIEWS.md for operational limits and the remaining access-permissions roadmap.


## Document/group permissions — 2026-10-17

The complete 92-test regression suite passed. A final eight-test permissions suite (including an additional legacy-provenance case), a targeted HTTP workflow-setting check and the Android Java HTTPS integration test also passed. Checks cover SQL filtering before retrieval/ranking, no model call without permitted evidence, private-before-indexing creation, group/CSRF boundaries, denied downloads, revocation in conversation history and completed jobs, transitive historical dependencies, canceled publication across access changes, retained policy metadata after document deletion, group removal remaining restricted, and watched replacements retaining grants.

The disposable browser preview verified group creation, document group selection, saving and reopening the permission policy, the new import-access choices, changing defaults for existing watched folders, and Persian document-access controls. Saved policies were reopened and verified, and the browser reported no console errors. Tests use temporary accounts, documents and policy only. Existing production permissions were not changed. See ACCESS-CONTROL.md for migration and revocation behavior, including conservative handling of legacy responses and the limits of recalling already delivered content.


## English OCR for scans — 2026-10-17

The complete 105-test suite passed, including 11 OCR tests and an HTTP test that the OCR on/off setting requires an administrator and CSRF and is saved to `config/server.json`. The OCR tests cover text cleanup (layout labels and pictures removed, tables kept as `cell | cell` rows, right-to-left table order), blank-page skipping and tile-grid sizing, loop, repeated-line and script detection, Persian and unreadable pages being reported instead of indexed, the note naming skipped pages, mixed PDFs where only text-less pages go to OCR, image files requiring OCR, the scanned-page limit, the message shown when OCR is off, and OCR defaults for older settings files. `manage.py check --full` passed and verified the OCR model checksums.

`tools/smoke_ocr.py` ran the real model end to end on generated English pages in a temporary copy. On the GPU, a scanned PDF page was read and indexed as `page 1 (OCR)`, a blank page was skipped without running the model, and a PNG took about 3.5 s. Pages with a few lines at the top, two columns or a ruled table returned 100% of words and numbers in 1–8 s. On the CPU (the default), a light page took about 36 s and a dense page about 2½ minutes. A dense page of 30 near-identical numbered lines made the model lose its place and re-read lines; the repeated-line check now reports such a page as unreadable instead of indexing it.

Not verified: real customer scans (stamps, handwriting, skew, poor copies), long scanned manuals under concurrent chat load, and installation on a clean machine. Persian OCR is deliberately off: in the evaluation it silently changed numbers, so Persian pages are reported and not indexed. See OCR.md and OCR-EVALUATION.md.
