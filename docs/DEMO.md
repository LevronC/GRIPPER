# Demo access

Demo credentials are for **development, preview, and evaluation only**. Do not use these passwords in production.

## Live demo

**URL:** https://gripper-ten.vercel.app/app

## Seeded demo account

When `SEED_DEMO_USER=true` (default in local dev and production), the API seeds:

| Field | Value |
|-------|--------|
| Institution | Stetson University |
| Email | `analyst@stetson.edu` |
| Password | `Gripp3rDemo!` |
| Role | analyst (verified) |

## Default institutions

| Institution | Slug |
|-------------|------|
| Stetson University | `stetson` |
| University of Florida | `uf` |
| RGIP Demo Program | `rgip-demo` |

## Register your own account

1. Open `/app?mode=register`
2. Use a `.edu` email and select your institution
3. Complete email verification (6-digit code is logged to the backend console in dev; check Vercel logs in production until email delivery is configured)

## Disabling demo seed in production

Set `SEED_DEMO_USER=false` in Vercel environment variables to stop seeding the shared demo password on startup. Institutions are still seeded.
