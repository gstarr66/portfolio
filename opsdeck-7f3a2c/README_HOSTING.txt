SurgiCentral — Static Portfolio Demo
=====================================

WHAT THIS IS
------------
A static (no server, no database) clone of the real SurgiCentral app,
built from the real templates and a real data snapshot taken 2026-07-23
while Gary still had access to the live server (192.168.1.17). It looks
and behaves like the live system, but nothing here is connected to a
database, QuickBooks, MongoDB, or WooCommerce. "Save" buttons on a
handful of signature flows fake success using your browser's
localStorage (see assets/js/site.js -> demoStore) so a demo click feels
real; refreshing after clearing site data resets everything to the
original snapshot. Everything else is read-only.

This shows real SurgiShop data under the real SurgiCentral/SurgiShop
name — by design, per Gary's decision, this is NOT meant to be public.
Password-gate it before uploading.

DEPLOYING ON APACHE / SHARED HOSTING
-------------------------------------
1. Upload the entire Clone/ folder to wherever you want it to live,
   e.g. https://yoursite.com/surgicentral-demo/
2. Create a password file (run this on the server, or locally if you
   have Apache's htpasswd tool, then upload the resulting file):

     htpasswd -c /path/outside/webroot/.htpasswd gary

   (drop the -c if the file already exists and you're adding a user)

3. Edit .htaccess in this folder and replace
   /FULL/SERVER/PATH/TO/.htpasswd with the real path to the file you
   just created. Putting it OUTSIDE the web-served folder is safest;
   if it must live inside this folder, the .htaccess already blocks
   direct requests to it.
4. Confirm your host has AllowOverride All (or equivalent) enabled for
   .htaccess to take effect — most shared hosts do by default; on a
   VPS running Apache you may need to enable it in the vhost config.

DEPLOYING ELSEWHERE (nginx / Netlify / etc.)
---------------------------------------------
.htaccess only works on Apache. If your host is something else, tell
Claude what it is and it'll translate this into the right mechanism
(nginx has an auth_basic directive; Netlify has a password-protect
feature in site settings; both are quick to set up).

IMPORTANT — DO NOT COPY THESE INTO Clone/
------------------------------------------
- _raw_db_backup_2026-07-23/  (sibling folder, one level up) — full raw
  data dump including live QBO OAuth tokens, user emails, and customer
  records. This is your private insurance copy, not part of the site.
- docker-compose.yml / config.py — contain real API secrets (QBO,
  Google OAuth, Mongo Atlas, SMTP). Never publish these anywhere.
