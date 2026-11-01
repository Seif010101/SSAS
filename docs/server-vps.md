# السيرفر على VPS من Hostinger (خطوة بخطوة، من غير خبرة)

**الفكرة:** بدل ما السيرفر يبقى كمبيوتر جوه المكان (docs/server-setup.md)، بنأجّر سيرفر صغير على النت (VPS) من Hostinger.
- الشاشات بتبعت النتايج عليه من أي مكان فيه نت.
- انت بتفتح صفحة الحضور من أي مكان: `https://api.ssas.ae`.
- **شهادة HTTPS حقيقية ومجانية** (Let's Encrypt) بتتعمل وتتجدد **لوحدها** عن طريق برنامج اسمه **Caddy**. يعني مفيش تحذير "غير آمن" في المتصفح، ومش محتاج fingerprint في Studio.

**إيه اللي بيروح للسيرفر؟** نص بس: مين حاضر ومين غايب، والأسماء.
- **مفيش ولا صورة** بتروح للسيرفر.
- **مفيش أي بيانات وش** بتروح للسيرفر.

```
 الشاشة ──HTTPS──►  api.ssas.ae (VPS)
                     ├── Caddy   (منفذ 80 و 443: الشهادة + بيوصّل الطلبات)
                     └── SSAS    (التطبيق، مقفول من بره، بيكلم Caddy بس)
```

---

## 1. تشتري الـ VPS
1. من hPanel في Hostinger: **VPS** ← اشتري أصغر خطة **KVM** (معالج واحد ورام 4 جيجا كفاية جداً).
2. لما يسألك عن نظام التشغيل (**Operating System**):
   - اختار **Ubuntu 24.04 with Docker**. ده موجود تحت **Applications** أو **OS with Panel**. الأحسن اللي فيه Docker جاهز.
   - ولو مش لاقيه: اختار **Ubuntu 24.04** عادي، وهنسطّب Docker في الخطوة 4.
3. اكتب **Root password** قوي، واحفظه في مكان آمن.
4. بعد ما يخلص (دقايق)، من **VPS ← Overview** انسخ الـ **IP** (زي `203.0.113.25`).

## 2. نربط اسم للسيرفر (DNS)
الموقع `ssas.ae` نفسه **مش هيتأثر**. إحنا بس بنعمل اسم فرعي جديد: `api.ssas.ae`.
1. hPanel ← **Domains** ← `ssas.ae` ← **DNS / Nameservers** ← **DNS records**.
2. **Add record:**
   - **Type:** `A`
   - **Name:** `api`
   - **Points to:** الـ IP بتاع الـ VPS
   - **TTL:** سيبه زي ما هو
3. احفظ. ممكن ياخد من دقايق لحد ساعة لحد ما يشتغل.
   - **علشان تتأكد:** افتح PowerShell على اللابتوب واكتب `nslookup api.ssas.ae`، لازم يطلع الـ IP بتاع الـ VPS.

## 3. نفتح شاشة الأوامر بتاعة السيرفر
- **أسهل طريقة:** hPanel ← **VPS** ← **Browser terminal**. هتفتح شاشة سودا في المتصفح نفسه.
- **أو** من PowerShell على اللابتوب: `ssh root@203.0.113.25` (حط الـ IP بتاعك)، واكتب الـ Root password.

كل الأوامر الجاية **انسخها والصقها** زي ما هي (لصق في Browser terminal: كليك يمين ← Paste، أو Ctrl+Shift+V).

## 4. نتأكد إن Docker موجود
```bash
docker --version
```
- لو طلع رقم نسخة، يبقى تمام.
- لو قال `command not found`، سطّبه:
```bash
curl -fsSL https://get.docker.com | sh
```

## 5. نحمّل برنامج السيرفر ونشغّله
```bash
mkdir -p /root/ssas && cd /root/ssas
wget https://github.com/Seif010101/SSAS/releases/latest/download/ssas-server.tar.gz
tar xzf ssas-server.tar.gz
cd server/deploy/vps
cp .env.example .env
nano .env
```
في `nano` غيّر السطرين دول:
```
SSAS_DOMAIN=api.ssas.ae
SSAS_ORG_NAME=اسم المكان (مدرسة / شركة / نادي...)
```
احفظ: **Ctrl+O** وبعدين **Enter**، واخرج: **Ctrl+X**.

بعدين شغّل:
```bash
docker compose up -d --build
docker compose ps
```
- لازم تشوف `ssas` و `caddy` الاتنين **Up**.
- اتفرّج على Caddy وهو بيجيب الشهادة:
```bash
docker compose logs -f caddy
```
  - استنى لحد ما تشوف `certificate obtained successfully`، وبعدين اضغط **Ctrl+C** (ده بيقفل العرض بس، والسيرفر بيفضل شغال).
  - لو ما ظهرتش بعد كام دقيقة، بص على جدول المشاكل تحت.

## 6. الجدار الناري (Firewall)
```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```
- منفذ **80** محتاجه Caddy علشان يجيب الشهادة ويحوّل أي حد بيفتح http لـ https.
- منفذ **443** للموقع والشاشات.
- **ولو Hostinger عنده Firewall في hPanel:** (VPS ← Security ← Firewall) اسمح بنفس المنافذ: 22 و 80 و 443.

## 7. حساب الأدمن (باسورد + كود 6 أرقام)
```bash
docker compose exec -it ssas python -m ssas_server.cli create-admin
```
- **الإيميل، والاسم، والدور:**
  - `developer` = **انت** (كل الصلاحيات).
  - `supervisor` = **مشرف** (يشوف بس).
- **كلمة السر:** 10 حروف أو أكتر. **ولأنه على النت، خليها طويلة وما تستخدمهاش في أي مكان تاني.**
- **صوّر الـ QR** بـ Google Authenticator أو Microsoft Authenticator.
- لو الـ QR طلع مكسّر في Browser terminal، اكتب المفتاح اللي تحته **بإيدك** في تطبيق الـ Authenticator.

## 8. جرّب الموقع
افتح `https://api.ssas.ae` من المتصفح:
- **مفيش أي تحذير**، لأن الشهادة حقيقية.
- سجّل دخول بالإيميل وكلمة السر والكود.

## 9. نربط Studio والشاشات
1. في **SSAS Studio ← Settings ← Server**:
   - **Server address:** `https://api.ssas.ae`
   - **Certificate fingerprint:** **سيبه فاضي** (الشاشة بتتأكد من الشهادة الحقيقية لوحدها).
   - اضغط **Save**.
2. اعمل **Export to USB** من الأول، و**Import** على كل شاشة.
3. في موقع السيرفر: **Boards** ← ارفع `SSAS-USB/server/boards.json`.
   - **مهم:** ارفعه تاني **بعد كل Export**، علشان السيرفر يعرف أي شخص جديد.
4. **الشاشات محتاجة نت** يوصل لـ `api.ssas.ae` على المنفذ 443.

## 10. حماية زيادة (مستحسن جداً على النت)
- **قفل صفحات الأدمن على عنوان المكتب بس.** الشاشات مش هتتأثر.
  1. اعرف عنوان المكتب من https://ifconfig.me (من جهاز في المكتب).
  2. اكتبه في `.env`:
     ```
     SSAS_ADMIN_ALLOW=203.0.113.7/32
     ```
  3. وبعدين: `docker compose up -d`
- **حدّث Ubuntu كل شهر:** `apt update && apt -y upgrade` (وبعدها `reboot` لو طلب).
- **ما تديش حد الـ Root password.** وما تسيبش فلاشة SSAS-USB في أي حتة، لأن فيها مفاتيح الشاشات.

## 11. نسخة احتياطية كل يوم
**على السيرفر نفسه** (الساعة 11 بالليل كل يوم):
```bash
crontab -e
```
اختار `nano` لو سألك، واكتب في آخر الملف:
```
0 23 * * * cd /root/ssas/server/deploy/vps && sh ../../backup.sh /root/ssas-backups >> /root/ssas-backup.log 2>&1
```
- السكريبت بيحتفظ بآخر **30 نسخة**.
- **ونسخة بره السيرفر كمان:** فعّل **Backups / Snapshots** من hPanel (VPS ← Backups).
- أو نزّل النسخ للابتوب كل فترة:
```powershell
scp -r root@203.0.113.25:/root/ssas-backups C:\SSAS-Backups
```

**ترجيع نسخة** (لو حصلت مشكلة كبيرة):
```bash
cd /root/ssas/server/deploy/vps
docker compose exec -T ssas sh -c 'cat > /data/restore.sqlite3' < /root/ssas-backups/ssas/ssas-YYYY-MM-DD_2300.sqlite3
docker compose exec -T ssas python -c "import sqlite3; sqlite3.connect('/data/restore.sqlite3').backup(sqlite3.connect('/data/ssas.sqlite3'))"
docker compose restart ssas
```

## 12. التحديث لنسخة جديدة
```bash
cd /root/ssas
wget -O ssas-server.tar.gz https://github.com/Seif010101/SSAS/releases/latest/download/ssas-server.tar.gz
tar xzf ssas-server.tar.gz
cd server/deploy/vps && docker compose up -d --build
```
**البيانات مش بتتمسح:** هي محفوظة في Docker volume اسمه `ssas_data`، والتحديث بيغيّر البرنامج بس. ملف `.env` كمان بيفضل زي ما هو.

## لو حصلت مشكلة
| المشكلة | السبب والحل |
|---|---|
| Caddy مش بيجيب شهادة | الـ DNS لسه ما اشتغلش: جرّب `nslookup api.ssas.ae`. أو منفذ 80 مقفول: راجع الخطوة 6. وبعدين `docker compose restart caddy`. |
| الصفحة بتقول 502 | التطبيق مش شغال: `docker compose logs --tail 50 ssas` |
| كود الـ 6 أرقام بيطلع غلط | ساعة الموبايل أو السيرفر غلط: `timedatectl` لازم يقول *System clock synchronized: yes* |
| الشاشة مش بتبعت | على الشاشة: القائمة المخفية ← **Show last results** (فيها السبب). وعلى السيرفر: صفحة **Boards** ← Last contact. |
| الشاشة بتقول "not registered" | ارفع `boards.json` الجديد بعد آخر Export. |
| نسيت كلمة السر | `docker compose exec -it ssas python -m ssas_server.cli set-password EMAIL` |
| الموبايل ضاع | `docker compose exec -it ssas python -m ssas_server.cli reset-totp EMAIL` |
