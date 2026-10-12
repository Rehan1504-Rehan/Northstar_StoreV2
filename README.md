# Northstar Store — Django E-Commerce

Northstar Store is a real, beginner-friendly Django 5 e-commerce application. It uses Django templates and Bootstrap 5 for the storefront, Django Admin for store operations, SQLite for local development, and PostgreSQL automatically when Railway provides a `DATABASE_URL`.

It is intentionally a simple order system: customers can place an order with shipping details, but no fake payment gateway is included.

## Live site 
- https://northstar-store.onrender.com
- The site is live but if render black interface comes please wait for 2 minutes for render to activate site.
## Features

- Customer registration with first name, last name, unique email validation, and Django password hashing.
- Login with either username or email, plus secure session logout.
- Product catalog with categories, product images, inventory, availability, sale pricing, and historical prices.
- Product search across name, description, and category.
- Category filtering.
- Persistent database cart for authenticated customers.
- Quantity validation so customers cannot add or order more than available stock.
- Transaction-safe checkout with locked inventory rows.
- Orders and order items stored permanently in the database.
- Product images stored in the database, so uploads survive redeploys on hosts with an ephemeral filesystem.
- Order items save the product name and price at purchase time. Later product price changes do not change old orders.
- Customer order history and order detail pages.
- Self-service order cancellation: customers can call off a Pending or Processing order from **My orders** or the order page, with a confirmation step, and every unit goes back into stock.
- Staff order cancellation from Django Admin with the same stock return behaviour.
- Customized Django Admin for products, images, categories, users, carts, orders, and order status.
- Product image preview in Admin.
- WhiteNoise static files, Gunicorn, PostgreSQL configuration through `DATABASE_URL`, and Railway deployment files.
- Friendly 403, 404, and 500 pages.
- Responsive Bootstrap 5 storefront for desktop, tablet, and mobile.

## Folder structure

```text
project_02/
├── manage.py
├── requirements.txt
├── Procfile
├── build.sh
├── runtime.txt
├── railway.json
├── .gitignore
├── .env.example
├── README.md
├── ecommerce/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── startup.py
│   ├── urls.py
│   └── wsgi.py
├── store/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── context_processors.py
│   ├── forms.py
│   ├── models.py
│   ├── storage.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   ├── 0002_alter_orderitem_product_name.py
│   │   └── 0003_mediafile.py
│   └── management/
│       ├── __init__.py
│       └── commands/
│           ├── __init__.py
│           ├── check_media.py
│           ├── create_admin.py
│           └── import_media_to_db.py
├── templates/
│   ├── 403.html
│   ├── 404.html
│   ├── 500.html
│   └── store/
│       ├── base.html
│       ├── home.html
│       ├── product_list.html
│       ├── product_detail.html
│       ├── register.html
│       ├── login.html
│       ├── cart.html
│       ├── checkout.html
│       ├── order_list.html
│       ├── order_detail.html
│       └── includes/product_card.html
├── static/
│   └── store/
│       ├── css/site.css
│       └── js/site.js
└── media/
    └── (legacy on-disk uploads; new uploads go to the database)
```

## Requirements

- Python 3.12 recommended (the repository includes `runtime.txt`).
- `pip`.
- SQLite locally, which is included with Python.
- PostgreSQL 13+ for production, supplied by Railway or another PostgreSQL host.

## Local setup on Windows

Open PowerShell or Command Prompt in the folder that contains `manage.py`.

### 1. Create and activate a virtual environment

PowerShell:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

Command Prompt:

```bat
python -m venv venv
venv\Scripts\activate
```

If PowerShell blocks activation, run this once in an Administrator PowerShell, or use Command Prompt:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Install the dependencies

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Create local environment variables

Copy `.env.example` to `.env` for local configuration and replace its placeholder values. The project loads that ignored `.env` file with `python-dotenv`; Railway variables still take precedence because they are already present in the environment. A brand-new local checkout also works without any variables because it uses a random development `SECRET_KEY`, `DEBUG=True`, and SQLite.

For a PowerShell session, example values are:

```powershell
$env:SECRET_KEY = "replace-this-with-a-long-random-development-key"
$env:DEBUG = "True"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
```

Do not commit a real `.env` file. It is ignored by Git.

### 4. Create the database tables

```bat
python manage.py makemigrations
python manage.py migrate
```

The repository already includes the initial migration. Running `makemigrations` again should report that there are no changes.

### 5. Create the administrator

Set the credentials only in your terminal, then run the safe custom command:

PowerShell:

```powershell
$env:ADMIN_USERNAME = "ADMIN"
$env:ADMIN_PASSWORD = "use-a-long-private-password-here"
$env:ADMIN_EMAIL = "admin@example.com"
python manage.py create_admin
```

Command Prompt:

```bat
set ADMIN_USERNAME=ADMIN
set ADMIN_PASSWORD=use-a-long-private-password-here
set ADMIN_EMAIL=admin@example.com
python manage.py create_admin
```

The command creates a Django superuser only if that username does not already exist. If it already exists, it makes no changes. The password is hashed by Django and is never stored in source code.

You can also create an admin interactively with `python manage.py createsuperuser`, but the environment-variable command is more convenient for Railway.

### 6. Run the development server

```bat
python manage.py runserver
```

Open:

- Storefront: <http://127.0.0.1:8000/>
- Admin dashboard: <http://127.0.0.1:8000/admin/>

## Using the site

### Add the first product

1. Open `/admin/` and sign in with the superuser credentials.
2. Select **Categories** and create a category such as `Electronics`.
3. Select **Products** and choose **Add product**.
4. Enter a name and description, price, optional discount price, stock quantity, and category.
5. Upload an image if desired.
6. Leave **Available** selected when the product should be visible to customers.
7. Click **Save**. The product appears on the home page and Shop all page if it has stock.

The admin list supports search, category/availability/date filters, inline price and inventory edits, and product image previews.

### Customer flow

1. A customer opens **Join us** and completes the registration form.
2. The user is permanently saved in Django's `auth_user` database table. Passwords are hashed using Django's password hasher.
3. The customer signs in with username or email.
4. They search or filter products, open details, choose a quantity, and add items to the database cart.
5. The cart prevents quantities above available stock.
6. Checkout validates the shipping address and phone number and creates the order in one database transaction.
7. Stock is reduced, the cart is cleared, and the order appears under **My orders**.
8. While the order is Pending or Processing, the customer can cancel it from **My orders** or the order page and get the stock back.

No payment gateway is simulated. Add a real payment provider only as a separate, deliberate feature.

### Update products and order status

In Admin, open **Products** to change prices, discount prices, descriptions, category, image, availability, and stock. Open **Orders** to review shipping information and change the status to Processing, Shipped, Delivered, or Cancelled. Old orders keep their `OrderItem.price` snapshot even after a catalog price edit.

To cancel an order as staff, select it in the **Orders** list and run the **Cancel selected orders and restock items** action. That action calls the same code path the storefront uses, so the units go back into stock and `cancelled_at` is recorded. Editing the `status` field to *Cancelled* by hand changes the label only — it does not return stock.

## Cancelling orders

Customers and staff share one cancellation routine (`Order.cancel()`), so both routes behave identically:

| | Customer (storefront) | Staff (Django Admin) |
| --- | --- | --- |
| How | **Cancel order** button on **My orders** or the order page | **Cancel selected orders and restock items** action |
| Confirmation | A modal asks for confirmation before anything changes | Django's action confirmation page |

**When an order can be cancelled.** Only while its status is **Pending** or **Processing**. Once it is **Shipped** or **Delivered** the button disappears and the customer is pointed at the returns policy instead. An order that is already **Cancelled** cannot be cancelled again.

**What happens when it is cancelled.**

- The status becomes `Cancelled` and `cancelled_at` is stamped with the time.
- Every line's quantity is added back to its product's `stock_quantity`.
- A product that checkout switched off because it sold out is switched back on, so returned units are visible to shoppers again. A product an admin switched off by hand while it still had stock stays off.
- The order stays in **My orders** with a cancelled badge, and the order page shows when it was cancelled.
- A product deleted from the catalog is skipped rather than causing an error, because `OrderItem.product` is `SET_NULL`.

The whole operation runs in one transaction with the order row and every product row locked, so a double click, or a customer and an admin cancelling at the same moment, cannot return the same stock twice.

The total is never refunded automatically: the project deliberately has no payment gateway, so a real deployment would add its refund step alongside this.

## Environment variables

| Variable | Local example | Production guidance |
| --- | --- | --- |
| `SECRET_KEY` | `a-long-random-string` | Required secret; never commit it. |
| `DEBUG` | `True` | Set `False`. |
| `DATABASE_URL` | empty for SQLite | Railway PostgreSQL supplies this automatically. |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Include the Railway public domain, comma separated. |
| `CSRF_TRUSTED_ORIGINS` | empty | Use full HTTPS origins, for example `https://your-app.up.railway.app`. |
| `ADMIN_USERNAME` | `ADMIN` | Private Railway variable. |
| `ADMIN_PASSWORD` | empty in Git | Private Railway variable; use a strong password. |
| `ADMIN_EMAIL` | `admin@example.com` | Private Railway variable. |
| `SECURE_SSL_REDIRECT` | `False` locally | Set `True` only when HTTPS proxy configuration is ready. |
| `MEDIA_STORAGE` | `database` | `database` (default) keeps uploads in the database so they survive redeploys. Use `filesystem` only with a real persistent disk. |
| `MEDIA_ROOT` | default `media/` | Only used when `MEDIA_STORAGE=filesystem`; point it at a mount such as `/data/media` (Render Persistent Disk) or `/app/media` (Railway Volume). |
| `SERVE_MEDIA` | `True` | Django serves `/media/` itself. Set `False` only when a CDN or object store answers that path. |
| `MEDIA_CACHE_SECONDS` | `3600` | Browser cache lifetime for uploaded images. ETags still allow instant revalidation. |
| `MAX_IMAGE_UPLOAD_MB` | `5` | Largest product image an admin may upload. Uploads are held in memory, so keep this modest. |
| `RUN_STARTUP_TASKS` | `True` | Applies pending migrations when the web process boots, and clears references to uploads lost to an earlier ephemeral filesystem. |

Django will use SQLite when `DATABASE_URL` is empty. When `DATABASE_URL` is set, `dj-database-url` configures the database, including Railway's PostgreSQL URL.

## Railway deployment

### 1. Push the project to GitHub

Create an empty GitHub repository, then from this project directory run the commands below. Replace only `YOUR_GITHUB_REPOSITORY_URL` with the HTTPS or SSH URL copied from your new GitHub repository:

```bat
git init
git add .
git commit -m "Initial Django ecommerce project"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

For example, the remote line could become:

```bat
git remote add origin https://github.com/your-user/northstar-store.git
```

Do not replace the project code with the URL; replace the placeholder only in the `git remote add origin ...` command.

### 2. Create the Railway project

1. Go to <https://railway.app> and create a new project.
2. Choose **Deploy from GitHub repo** and select this repository.
3. Railway detects the `Procfile` and `runtime.txt` and runs Gunicorn with `ecommerce.wsgi`.
4. Click **New** → **Database** → **Add PostgreSQL**. Railway makes the database connection available to the application as `DATABASE_URL` when the PostgreSQL service is linked to the web service.

### 3. Add variables to the Railway web service

Open the web service (not only the PostgreSQL service), choose **Variables**, and add these values:

```text
SECRET_KEY=<generate-a-long-random-secret>
DEBUG=False
ALLOWED_HOSTS=<your-railway-domain>,<optional-custom-domain>
CSRF_TRUSTED_ORIGINS=https://<your-railway-domain>
ADMIN_USERNAME=ADMIN
ADMIN_PASSWORD=<strong-private-admin-password>
ADMIN_EMAIL=admin@example.com
SECURE_SSL_REDIRECT=False
```

Use Railway's **Generate** option for `SECRET_KEY` if available. Replace the angle-bracket values with real deployment values. Do not put the password in GitHub, README files, HTML, JavaScript, or Python source.

`ALLOWED_HOSTS` is a comma-separated list without `https://`. `CSRF_TRUSTED_ORIGINS` is a comma-separated list of full origins with `https://`.

### 4. Run database and setup commands

After the PostgreSQL service is linked and variables are saved, open the web service's Railway shell and run:

```text
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py create_admin
```

The `create_admin` command reads `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_EMAIL` from Railway Variables. Running it again is safe: if the username exists, it does nothing.

You can rerun these commands after a deployment. For repeatable automated deployments, use them as a Railway pre-deploy/release command in your service configuration. Keep `create_admin` after migrations and keep the password only in Railway Variables.

### 5. Generate a public domain

In the Railway web service, open **Settings** → **Networking** → **Generate Domain**. Put that hostname into `ALLOWED_HOSTS` and its `https://` origin into `CSRF_TRUSTED_ORIGINS`, then redeploy. Open the generated public URL and test `/`, `/register/`, and `/admin/`.

### 6. Static files and media files

- WhiteNoise serves files collected into `staticfiles/`; the Procfile starts Gunicorn with the correct WSGI module.
- `python manage.py collectstatic --noinput` is safe to run during deployment.
- **Product uploads are stored in the database**, not on disk. Cloud container filesystems (Render, Railway, Fly.io, Heroku) are ephemeral: a file written to `MEDIA_ROOT` is deleted on the next deploy or restart, while the product row keeps pointing at it, which is why images used to turn into broken `404`s. Keeping the bytes in the database makes an image last exactly as long as its product, with no persistent disk or object-storage account required.
- Django serves the files back at `/media/<path>` with correct content types, `ETag` revalidation and a `Cache-Control` lifetime of `MEDIA_CACHE_SECONDS`.
- Because uploads are read into memory and stored in a row, `MAX_IMAGE_UPLOAD_MB` (default 5 MB) caps their size. Web-friendly images of 200-500 KB are ideal.
- Replaced and deleted product images are removed from storage automatically, so the table does not grow without bound.
- Prefer a mounted disk instead? Set `MEDIA_STORAGE=filesystem` plus `MEDIA_ROOT`, attach a Render Persistent Disk at `/data/media` or a Railway Volume at `/app/media`, and run `python manage.py import_media_to_db` beforehand if files already live in the database.
- For a multi-instance or higher-traffic shop, use an S3-compatible object store (Amazon S3, Cloudflare R2, or similar) and add a dedicated Django storage backend such as `django-storages`. Point `STORAGES["default"]` at that backend and set `SERVE_MEDIA=False`; keep its bucket credentials as private service variables and never place cloud keys in this repository. Static files can continue to use WhiteNoise.

### Media storage commands

| Command | Purpose |
| --- | --- |
| `python manage.py check_media` | Lists products whose image file is missing from storage, plus stored files no product references. |
| `python manage.py check_media --clear-missing` | Blanks broken image references so the storefront shows its neutral placeholder instead of a broken image. |
| `python manage.py check_media --prune-orphans` | Deletes stored files that no product uses. |
| `python manage.py import_media_to_db` | Copies files from `MEDIA_ROOT` into the database; run once when moving off a disk. |

## Render deployment

Render builds from the repository and runs the app as a web service.

| Setting | Value |
| --- | --- |
| Build command | `./build.sh` (installs dependencies, collects static files, runs migrations) |
| Start command | `gunicorn ecommerce.wsgi --log-file -` |

The app also applies any pending migrations itself when the web process boots,
so a service that only sets a start command still ends up with a correct
database. `build.sh` is still the tidier place to do it, because migrating
during the build keeps boots fast. Set `RUN_STARTUP_TASKS=False` to turn the
startup behaviour off.

Required environment variables on the web service:

```
SECRET_KEY=<a long random value>
DEBUG=False
ALLOWED_HOSTS=your-app.onrender.com
CSRF_TRUSTED_ORIGINS=https://your-app.onrender.com
DATABASE_URL=<the Internal Database URL of a Render PostgreSQL instance>
```

`DATABASE_URL` is not optional in production. Render's container filesystem is
wiped on every deploy and whenever a free instance wakes from sleep, so a SQLite
file stored there loses all products, orders and images. Attach a managed
PostgreSQL database and the data - including the product images, which are
stored in the database - persists.

On its first boot after this change the app also clears product images whose
file was destroyed by an earlier redeploy, so the storefront shows its neutral
placeholder instead of a broken image. Upload those pictures again in Django
Admin and they will persist from then on.

## Database and price behavior

The checkout uses `transaction.atomic()` and locks the cart and product rows while validating inventory. It creates the `Order`, all `OrderItem` rows, reduces stock, and clears the cart as one unit. If validation fails, no partial order remains.

Each `OrderItem` has:

- `product`: a nullable reference to the current catalog product;
- `product_name`: a readable name snapshot;
- `price`: the exact price at the time of purchase;
- `quantity`.

The order pages render `OrderItem.price`, not the current `Product.price`, so changing a product's price later cannot rewrite an old order.

Cancellation is the mirror image of checkout and is just as careful: `Order.cancel()` re-reads the order with `select_for_update()` inside a transaction, refuses any order past the Pending/Processing window, and returns each line's quantity to its locked product row. Calling it twice is safe — the second call reports that nothing was cancelled rather than restocking again. See [Cancelling orders](#cancelling-orders).

## Testing and useful commands

Run Django's checks, migrations, static collection, and the test suite:

```bat
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py test
```

Check which migrations are applied:

```bat
python manage.py showmigrations
```

Start Gunicorn locally (PowerShell or Command Prompt):

```bat
gunicorn ecommerce.wsgi --workers 2 --threads 4 --timeout 60 --graceful-timeout 30 --log-file -
```

On Windows, Gunicorn is primarily intended for Railway/Linux. Use `python manage.py runserver` for local Windows development.

## Troubleshooting

### `DisallowedHost` on Railway

Add the exact generated Railway hostname, without `https://`, to `ALLOWED_HOSTS`, save the variable, and redeploy.

### CSRF verification failed

Set `CSRF_TRUSTED_ORIGINS` to the full URL, including `https://`, for the public Railway domain. Do not use a bare hostname in this setting.

### Database connection errors

Confirm PostgreSQL is linked to the web service and that `DATABASE_URL` appears in the service variables. Run `python manage.py migrate` from the web service shell, not only from the database service.

### Images disappear after a redeploy

This is fixed: product images are stored in the database (`MEDIA_STORAGE=database`, the default), so they now survive deploys, restarts and free-tier sleep cycles. Two things must be true on the host:

1. The deploy runs `python manage.py migrate --noinput`, which creates the `store_mediafile` table. `build.sh` already does this.
2. `DATABASE_URL` points at a managed PostgreSQL database. With the default SQLite file, the database itself sits on the ephemeral disk, so products *and* images would still be lost.

Images uploaded **before** this change were written to the old ephemeral disk and are gone for good. Find and clear those dangling references, then re-upload the pictures:

```bash
python manage.py check_media                  # list products whose file is missing
python manage.py check_media --clear-missing  # blank them so the placeholder shows
```

If you are migrating from a working persistent disk, copy those files into the database first:

```bash
python manage.py import_media_to_db
```

### Static assets are missing

Run `python manage.py collectstatic --noinput`, confirm `DEBUG=False` is not combined with a missing `STATIC_ROOT`, and check that the service uses `gunicorn ecommerce.wsgi` from the project directory.

### Admin login does not work

Run migrations, confirm the Railway variables are set on the web service, and run `python manage.py create_admin` again. An existing username is intentionally not changed by the command; use Django's password reset workflow or create a different admin account if needed.

### `discount_price` validation error

A discount price must be lower than the regular price. Leave it blank for a product with no discount.

## Security notes

- Never commit `.env`, database credentials, `SECRET_KEY`, or the admin password.
- CSRF tokens are included on all state-changing storefront forms.
- The admin uses Django's built-in permission and password systems.
- Production should use `DEBUG=False`, HTTPS, a restricted `ALLOWED_HOSTS`, a trusted CSRF origin list, and persistent media storage.


## ShopVerse template integration

The storefront adapts the design from [Rehan1504-Rehan/abcd](https://github.com/Rehan1504-Rehan/abcd), specifically `ecommece template 4 (final)`. Northstar branding, INR prices, and all Django commerce flows are retained.

- `static/store/css/shopverse.css`: namespaced template hero, service, category, and responsive styles; isolated from Bootstrap dialogs and forms.
- `static/store/css/template-theme.css`: shared Northstar theme and accessibility/responsive overrides.
- `templates/store/home.html`: template-inspired hero and category tiles using live catalog data.
- The existing Django product cards, search, account pages, cart, checkout, and order history remain authoritative. No demo products, fake reviews, countdowns, simulated payments, or local-storage cart were imported.
- The hero uses the first featured product and displays a styled placeholder when an image or catalog is absent. Categories and deals populate from Django Admin.
- Poppins and icon fonts use external CDNs, as do the existing Bootstrap assets. No additional build step is needed.

Validate with `python manage.py check` and `python manage.py test`.
