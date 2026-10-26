# تجهيز كمبيوتر المعمل كسيرفر (خطوة بخطوة)

السيرفر **مش بيحلل صور**. اللابتوب هو اللي بيدرّب، والشاشة هي اللي بتتعرف على الطلاب. السيرفر بس بيستقبل نتايج الحضور من الشاشات (نص) وبيعرضها للأدمن. علشان كده أي كمبيوتر قديم ينفع.

**المطلوب:**
- الكمبيوتر نفسه:
  - **64-bit**.
  - **رام 4 جيجا أو أكتر** (عندك 8، ممتاز).
  - هارد 60 جيجا أو أكتر (لو SSD يبقى أحسن).
  - **ملحوظة:** الكمبيوتر ده **هيتمسح بالكامل**.
- فلاشة 8 جيجا علشان تسطيب Ubuntu (مش فلاشة SSAS).
- شاشة وكيبورد **وقت التسطيب بس**. بعد كده بنتحكم فيه من اللابتوب.
- إنترنت وقت التسطيب.

---

## 1. نعمل فلاشة تسطيب Ubuntu
1. من أي كمبيوتر Windows، حمّل **Ubuntu Server 24.04 LTS** من: https://ubuntu.com/download/server (اختار *Option 2 – Manual installation*، والملف اسمه `ubuntu-24.04.x-live-server-amd64.iso`).
2. حمّل برنامج **Rufus** من: https://rufus.ie
3. شغّل Rufus ← اختار الفلاشة ← SELECT واختار ملف الـ ISO ← START ← لو سألك، اختار *Write in ISO Image mode* ← OK.

## 2. إعدادات الـ BIOS (مرة واحدة)
1. وصّل الفلاشة في كمبيوتر المعمل، وشغّله وانت ضاغط على **F2** أو **Del** (ولو مدخلش، جرّب F10 أو F12 أو Esc).
2. دوّر على **Restore on AC Power Loss** (أو *After Power Failure*) وخليها **Power On**. كده لو الكهرباء قطعت ورجعت، السيرفر يشتغل لوحده.
3. خلّي أول حاجة يبدأ منها الجهاز (Boot) هي **الفلاشة**، واعمل Save و Exit.

## 3. تسطيب Ubuntu Server
اختار الحاجات دي بالترتيب:

| الشاشة | اختار |
|---|---|
| Language | English |
| Keyboard | English (US) |
| Type of install | **Ubuntu Server (minimized)** |
| Network | سيبها زي ما هي (DHCP). **واكتب الـ IP اللي هيظهر**، زي `192.168.1.10` |
| Proxy / Mirror | سيبهم زي ما هم |
| Storage | **Use an entire disk** ← Done ← Continue (ده بيمسح الهارد) |
| Profile | Your name: `SSAS` · Server name: `ssas-server` · Username: `ssas` · كلمة سر قوية **واكتبها في ورقة وخليها في مكان آمن** |
| Ubuntu Pro | Skip |
| SSH | ✅ **Install OpenSSH server** |
| Snaps | متختارش حاجة |

لما التسطيب يخلص اضغط **Reboot Now**، وشيل الفلاشة.

## 4. نثبّت عنوان السيرفر (IP)
الشاشات لازم تلاقي السيرفر على **نفس العنوان** كل يوم. فيه طريقتين:
- **الأسهل والأفضل:** اطلب من الـ IT يعملوا **DHCP Reservation** في الراوتر، علشان العنوان ده (زي `192.168.1.10`) يفضل ثابت لكمبيوتر السيرفر.
- **أو من السيرفر نفسه** (لو الـ IT مش موجود):
  1. اكتب `ip a` علشان تعرف اسم كارت الشبكة (زي `enp2s0`).
  2. وبعدين اكتب:
```bash
sudo nano /etc/netplan/50-cloud-init.yaml
```
  3. امسح الموجود في الملف، واكتب ده (وغيّر الأرقام على حسب شبكتك):
```yaml
network:
  version: 2
  ethernets:
    enp2s0:
      dhcp4: false
      addresses: [192.168.1.10/24]
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses: [1.1.1.1, 8.8.8.8]
```
  4. احفظ (Ctrl+O، وبعدين Enter، وبعدين Ctrl+X)، وبعدين اكتب: `sudo netplan apply`

## 5. من دلوقتي نشتغل من اللابتوب
على اللابتوب افتح **PowerShell** واكتب:
```powershell
ssh ssas@192.168.1.10
```
لو سألك اكتب `yes`، وبعدين اكتب كلمة السر. **الشاشة والكيبورد اللي على السيرفر مبقاش لهم لازمة.**

## 6. تحديث النظام وتسطيب Docker
```bash
sudo apt update && sudo apt full-upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ssas
exit
```
اخرج واعمل `ssh` تاني علشان صلاحية Docker تشتغل. التحديثات الأمنية التلقائية شغالة في Ubuntu من الأول.

## 7. تحميل برنامج السيرفر وتشغيله
```bash
cd ~
wget https://github.com/Seif010101/SSAS/releases/latest/download/ssas-server-0.1.0.tar.gz
tar xzf ssas-server-0.1.0.tar.gz
cd server
cp .env.example .env
nano .env            # اكتب اسم المدرسة في SSAS_SCHOOL_NAME، وبعدين احفظ
docker compose up -d --build
docker compose ps    # لازم يكتب "running"
```
(لو رقم النسخة اتغير، غيّره في أول سطرين.)

## 8. حسابات الأدمن (باسورد + كود من 6 أرقام)
لكل أدمن (انت والمشرف):
```bash
docker compose exec -it ssas python -m ssas_server.cli create-admin
```
- **الإيميل والاسم:** اكتبهم.
- **الدور (Role):**
  - `developer` = **انت**، وليك كل الصلاحيات.
  - `supervisor` = **المشرف**، وده **عرض فقط**.
- **كلمة السر:** 10 حروف أو أكتر.
- **الـ QR:** هيظهر QR على الشاشة. افتح **Google Authenticator** أو **Microsoft Authenticator** على الموبايل وصوّره.

أوامر تانية ممكن تحتاجها:
- `... cli list-admins` (تعرض الأدمنز).
- `... cli reset-totp EMAIL` (لو الموبايل ضاع).
- `... cli set-password EMAIL` (لو نسيت كلمة السر).

## 9. نربط برنامج اللابتوب والشاشات بالسيرفر
1. على السيرفر اكتب:
```bash
docker compose exec ssas python -m ssas_server.cli show-cert-fingerprint
```
   وانسخ الرقم الطويل اللي هيطلع.
2. في **SSAS Studio** افتح **Settings ← Server**:
   - **Server address:** `https://192.168.1.10`
   - **Certificate fingerprint:** الرقم اللي نسخته.

   بعدين **Save**، وبعدين اعمل **Export to USB** من الأول.
3. افتح من المتصفح `https://192.168.1.10`:
   - المتصفح هيقول إن الاتصال "غير آمن"، لأن الشهادة بتاعتنا إحنا. اضغط **Advanced** وبعدين **Continue / Proceed**.
   - **الشاشات نفسها ما بتطلعش التحذير ده**، لأنها بتتأكد من البصمة اللي فوق.
4. سجّل دخول، وبعدين روح **Boards**، وارفع الملف `SSAS-USB/server/boards.json` اللي على الفلاشة.

## 10. الجدار الناري
```bash
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw enable
```
**مهم للشبكة:**
- الشاشات لازم توصل لـ IP السيرفر على **المنفذ 443**.
- لو كل جهاز على شبكة مختلفة، اطلب من الـ IT يسمحوا بده من شبكة الشاشات.
- **شبكة الطلاب وشبكة الضيوف ممنوع توصل للسيرفر.**
- اقفل الـ Hotspot بتاع كل شاشة، أو حط له باسورد قوي.

## 11. نسخة احتياطية كل يوم (على هارد أو فلاشة USB)
1. ركّب الهارد مرة واحدة:
```bash
lsblk                                   # اعرف اسمه، مثلاً sdb1
sudo mkdir -p /mnt/backup
sudo blkid /dev/sdb1                    # انسخ قيمة UUID
echo 'UUID=xxxx-xxxx /mnt/backup auto defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a
```
2. اعمل النسخة تتعمل لوحدها كل يوم الساعة 6 مساءً:
```bash
crontab -e
# اكتب السطر ده في الآخر:
0 18 * * * /home/ssas/server/backup.sh /mnt/backup >> /home/ssas/backup.log 2>&1
```
السكريبت بيحتفظ بآخر 30 نسخة. **ولازم تجرّب ترجّع نسخة مرة كل ترم.**

## 12. التحديث لنسخة جديدة
```bash
cd ~ && wget https://github.com/Seif010101/SSAS/releases/latest/download/ssas-server-X.Y.Z.tar.gz
tar xzf ssas-server-X.Y.Z.tar.gz        # بيستبدل الملفات من غير ما يلمس data/ و .env
cd server && docker compose up -d --build
```

## لو حصلت مشكلة
| المشكلة | الحل |
|---|---|
| الصفحة مش بتفتح | `docker compose ps` و `docker compose logs --tail 50` |
| كود الـ 6 أرقام بيطلع غلط | تأكد من الوقت بالأمر `timedatectl` (لازم يكون فيه *System clock synchronized: yes*) |
| الشاشة مش بتبعت | من الشاشة: القائمة المخفية ← Show last results. ومن السيرفر: صفحة Boards ← Last contact |
| السيرفر اتنقل لمكان تاني أو الـ IP اتغير | غيّر Server address في Studio وصدّر الفلاشة من الأول |
