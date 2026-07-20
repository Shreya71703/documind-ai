# Deploying DocuMind AI — Oracle Cloud (Always Free)

This guide walks you through deploying DocuMind AI on **Oracle Cloud's Always Free Tier** — at **zero cost, forever**.

You will get a cloud VM with up to **4 CPU cores, 24 GB RAM, and 200 GB storage** — more than enough to run the entire Docker Compose stack.

---

## Prerequisites

- A Google account (for Gemini API key)
- A credit/debit card (Oracle requires it for identity verification — **you will NOT be charged**)

---

## Step 1 — Create an Oracle Cloud Account

1. Go to [https://cloud.oracle.com](https://cloud.oracle.com) and click **Sign Up**.
2. Choose **Free Tier** during signup.
3. Select your **Home Region** — pick the one closest to you (e.g., `ap-mumbai-1` for India).
4. Complete verification with your card — Oracle will place a temporary ₹0 hold and release it.

---

## Step 2 — Create an Always Free VM

1. In the Oracle Cloud Console, go to **Compute → Instances → Create Instance**.
2. Configure the instance:

   | Setting | Value |
   |---|---|
   | **Name** | `documind-ai` |
   | **Image** | Ubuntu 22.04 (or 24.04) — Canonical |
   | **Shape** | **VM.Standard.A1.Flex** (Ampere ARM — Always Free) |
   | **OCPUs** | 2 |
   | **Memory** | 12 GB |
   | **Boot volume** | 50 GB (Always Free allows up to 200 GB total) |

3. Under **Networking**, make sure **Assign a public IPv4 address** is selected.
4. Under **Add SSH keys**, either:
   - Upload your existing `~/.ssh/id_rsa.pub` key, **or**
   - Let Oracle generate a key pair and **download the private key** (save it safely — you need it to SSH in).
5. Click **Create**.

> **Note:** If the shape shows "Out of capacity", try again in a few hours or switch to a different Availability Domain. The Always Free ARM instances are popular and sometimes temporarily unavailable.

---

## Step 3 — Open Firewall Ports

Oracle's default security list blocks all incoming traffic except SSH. You need to open ports **3000** (frontend) and **8000** (backend API).

1. Go to **Networking → Virtual Cloud Networks** → click your VCN.
2. Click the **Public Subnet** → click the **Default Security List**.
3. Click **Add Ingress Rules** and add these two rules:

   | Source CIDR | Protocol | Destination Port | Description |
   |---|---|---|---|
   | `0.0.0.0/0` | TCP | `3000` | DocuMind Frontend |
   | `0.0.0.0/0` | TCP | `8000` | DocuMind Backend API |

4. Click **Add Ingress Rules** to save.

---

## Step 4 — SSH into Your VM

Find your VM's **Public IP Address** on the Instance Details page, then connect:

```bash
# If Oracle generated the key for you:
ssh -i ~/path/to/your-private-key.key ubuntu@<YOUR_VM_PUBLIC_IP>

# If you used your own key:
ssh ubuntu@<YOUR_VM_PUBLIC_IP>
```

---

## Step 5 — Install Docker

Run these commands on the VM:

```bash
# Update system packages
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (avoids needing sudo for every docker command)
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt-get install -y docker-compose-plugin

# Apply group changes (or log out and back in)
newgrp docker

# Verify installation
docker --version
docker compose version
```

---

## Step 6 — Open Firewall Ports on the VM (iptables)

Oracle Cloud uses **both** a cloud security list (Step 3) **and** the VM's internal firewall. You need to allow ports on both:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT

# Save the rules so they persist after reboot
sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

---

## Step 7 — Clone and Configure DocuMind AI

```bash
# Clone the repository
git clone https://github.com/Shreya71703/documind-ai.git
cd documind-ai

# Create the backend environment file
cp backend/.env.example backend/.env
```

Now edit the `.env` file with your real keys:

```bash
nano backend/.env
```

Update these values:

```env
DATABASE_URL=postgresql+asyncpg://rag_user:rag_password@db:5432/rag_db
CHROMA_PERSIST_DIRECTORY=chroma_db
AI_PROVIDER=gemini
GEMINI_API_KEY=<paste_your_real_gemini_api_key>
GEMINI_CHAT_MODEL=gemini-1.5-flash
GEMINI_EMBEDDING_MODEL=text-embedding-004
JWT_SECRET=<generate_a_random_string_at_least_32_chars>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

> **Tip:** Generate a secure JWT secret with: `openssl rand -hex 32`

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X` in nano).

---

## Step 8 — Update Frontend API URL

The frontend is built at Docker image build time, so the API URL is baked into the production bundle. You need to point it at your VM's public IP.

```bash
# Create the frontend env file
echo "VITE_API_BASE_URL=http://<YOUR_VM_PUBLIC_IP>:8000" > frontend/.env
```

Replace `<YOUR_VM_PUBLIC_IP>` with your actual VM IP address (e.g., `129.154.52.100`).

---

## Step 9 — Build and Launch

```bash
docker compose up --build -d
```

This will:
- Build the backend and frontend Docker images
- Start PostgreSQL, wait for it to be healthy
- Start the FastAPI backend
- Start the Nginx frontend

> **First build takes ~5–10 minutes** on the ARM VM. Subsequent builds use Docker's cache and are much faster.

---

## Step 10 — Run Database Migrations

```bash
docker compose exec backend alembic upgrade head
```

---

## Step 11 — Verify Everything is Running

```bash
# Check all containers are up
docker compose ps

# Expected output:
# rag-postgres    running (healthy)
# rag-backend     running
# rag-frontend    running

# Quick health check
curl http://localhost:8000/api/v1/docs
curl http://localhost:3000
```

---

## 🎉 Access Your Live App

Open a browser and go to:

| Service | URL |
|---|---|
| **Frontend** | `http://<YOUR_VM_PUBLIC_IP>:3000` |
| **API Docs** | `http://<YOUR_VM_PUBLIC_IP>:8000/api/v1/docs` |

Create an account and start uploading documents!

---

## Useful Commands

```bash
# View live logs
docker compose logs -f

# View logs for a specific service
docker compose logs -f backend

# Restart the stack
docker compose restart

# Stop everything
docker compose down

# Stop and remove all data (database, vectors, uploads)
docker compose down -v

# Rebuild after code changes
docker compose up --build -d
```

---

## Updating After a Git Push

When you push new code to GitHub:

```bash
cd ~/documind-ai
git pull
docker compose up --build -d
```

---

## Optional — Custom Domain (Free)

If you want a clean URL instead of a raw IP address:

1. Get a free domain from [Freenom](https://www.freenom.com) or use a subdomain from [DuckDNS](https://www.duckdns.org).
2. Point the domain's A record to your VM's public IP.
3. For HTTPS, install [Caddy](https://caddyserver.com) as a reverse proxy (it handles SSL certificates automatically for free via Let's Encrypt).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Can't access from browser | Check both Oracle Security List (Step 3) AND iptables rules (Step 6) |
| `docker compose` not found | Use `docker-compose` (with hyphen) or install the plugin: `sudo apt-get install docker-compose-plugin` |
| Backend crashes on startup | Check logs: `docker compose logs backend` — usually a missing env variable |
| "Out of capacity" when creating VM | Try a different Availability Domain, or wait a few hours and retry |
| Frontend shows network error | Make sure `frontend/.env` has the correct `VITE_API_BASE_URL` with your public IP, then rebuild |
