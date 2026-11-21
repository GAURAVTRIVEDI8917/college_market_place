# CampusMart

CampusMart is a Flask and SQLite second-hand marketplace for college students.
Buyers can submit order requests and sellers confirm them directly. Online
checkout and payment processing are not configured in this project.

## Features

- Student sign-up and login with hashed passwords
- Account settings for profile, WhatsApp phone, and password updates
- Product listings with image, category, price, description, and seller
- Search and category filters
- Product details and email contact with the seller
- Buyer order requests, seller confirmations, and order status tracking
- Shareable product links using the device share menu or copy-link fallback
- Required seller mobile number on every listing, with optional WhatsApp contact
- Saved/favorite products for signed-in students
- Seller listing edits and sold/available status controls
- One editable rating and review per student for each product
- Seller listing management, account suspension, and administrator moderation

## Run locally

From the project folder, run:

```powershell
python app.py
```

Open `http://127.0.0.1:5000`. The app creates or upgrades `database.db` on startup.
Product images are stored under `static/images`.

## Create a public demo link with Render

1. Push this project to a GitHub repository that you control.
2. In Render, choose **New +** → **Blueprint** and connect that repository.
3. Keep the `campusmart` web service on the free plan for a temporary demo.
4. Enter your admin email when Render prompts for `CAMPUSMART_ADMIN_EMAIL`.
5. After deployment succeeds, open the `onrender.com` URL shown on the Render service page.
6. Sign up with the admin email, then sign in to use the **Admin** link.

The included `render.yaml` configures the service, generated secret key, and
startup command. A free demo service uses temporary local storage: database
accounts, listings, and uploaded images may be lost on redeploy or restart.
Do not use it for real marketplace data or passwords. Persistent data requires
separately configured durable database and file storage.

## Configure the administrator for a demo

Before starting the app, set the administrator email in PowerShell:

```powershell
$env:CAMPUSMART_ADMIN_EMAIL = "admin@example.com"
python app.py
```

Replace the example with your admin account email and run both commands in the
project folder. Restart the server after changing the setting. Create an account
with that email using **Sign Up**, or log out and back in if it already exists.
The **Admin** link appears after login. Each startup grants admin access to the
configured email and removes admin access from other accounts. Leave
`CAMPUSMART_ADMIN_EMAIL` unset to disable administrator access. For a persistent
deployment, also set a private `CAMPUSMART_SECRET_KEY` environment variable.

## Quick troubleshooting

- **My Listings:** log in with the same account that created the listings. Each
  student sees only their own listings there.
- **Admin link missing:** set `CAMPUSMART_ADMIN_EMAIL` to the account email,
  restart the app, then log out and back in. The `/admin` page requires that role.

## Presentation walkthrough

1. Sign up as a student and log in.
2. Add a listing with a photo, then find it using search or a category filter.
3. Open its details and show the seller contact link.
4. Sign in with a second account to leave a rating and review.
5. Request an available item, then open **Orders** to track it; sellers can confirm or decline requests.
6. Save a product, then open **Saved**; use **My Listings** to edit a listing or mark it sold.
7. Open **Account** to add a WhatsApp number or change the password.
8. Sign in using the configured administrator email to show account, listing, and review moderation.
   Suspend and then reactivate the demo student account to show both account states.
