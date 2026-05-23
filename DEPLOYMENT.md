# Rational Equity - Free Hosting Setup

## Quick Deploy Instructions

### Prerequisites
1. GitHub account
2. Render.com account (no credit card needed)

### Deployment Steps

1. **Push to GitHub**
   ```bash
   cd /home/kplinux/Downloads/projects/stockguide
   git init
   git add .
   git commit -m "Initial commit - Rational Equity Dashboard"
   
   # Create GitHub repo first, then:
   git remote add origin https://github.com/YOUR_USERNAME/rational-equity.git
   git push -u origin main
   ```

2. **Deploy on Render**
   - Visit https://dashboard.render.com
   - Click "New +" → "Web Service"
   - Connect GitHub account
   - Select your repository
   - Render auto-detects `render.yaml`
   - Click "Create Web Service"

3. **Access Your Dashboard**
   - Your app will be at: `https://rational-equity-XXXXX.onrender.com`
   - First load takes 30-60s (building)
   - Subsequent loads: instant (if within 15min) or 30-60s (cold start)

### Keep-Alive (Optional)

To prevent cold starts, use cron-job.org:
1. Visit https://cron-job.org
2. Create free account
3. Add job: Ping your Render URL every 10 minutes

### Environment Variables

If you have API keys:
1. Render Dashboard → Your Service → "Environment"
2. Add variables (they'll be available as env vars)

---

## Project Structure

```
stockguide/
├── render.yaml          # Render configuration
├── requirements.txt     # Python dependencies
├── start.sh            # Local development launcher
├── README.md           # This file
└── stockguide/
    ├── .env            # Local env vars (not deployed)
    ├── backend/        # FastAPI application
    │   ├── main.py
    │   ├── dip_hunter.py
    │   └── ...
    └── frontend/       # Static HTML/JS/CSS
        ├── index.html
        ├── app.js
        └── ...
```

---

## Local Development

```bash
./start.sh
# Opens at http://localhost:8000
```

## Deployment

```bash
git add .
git commit -m "Your changes"
git push
# Render auto-deploys!
```
