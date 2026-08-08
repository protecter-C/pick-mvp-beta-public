# Production deployment checklist

## Required environment

Set the variables in `services/api/.env.production.example` through the deployment secret manager. Do not commit the populated file.

## API deploy, migrate, and start

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the migration command once per release before starting additional API workers. The API process must receive the same production environment variables.

## Web deploy/start

```powershell
cd apps/web
npm ci
npm run build
npm run start
```

Set `NEXT_PUBLIC_API_URL` to the deployed API origin at web build time.

## Mobile release build

```powershell
cd apps/mobile
flutter pub get
flutter build apk --release --dart-define=API_URL=https://api.example.com
```
