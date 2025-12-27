# Deploying Photostream to Backblaze B2 + Cloudflare Workers

This guide covers deploying your Photostream gallery to Backblaze B2 storage with a Cloudflare Worker for caching and serving.

## Architecture

- **Backblaze B2**: Cost-effective object storage for your gallery files
- **Cloudflare Worker**: Edge proxy with intelligent caching and routing
- **Benefits**: Low cost, global CDN, fast loading, no server management

## Prerequisites

1. **Backblaze B2 Account**
   - Sign up at https://www.backblaze.com/b2
   - Create a bucket (public or private)
   - Generate application key with read/write access

2. **Cloudflare Account**
   - Sign up at https://www.cloudflare.com
   - Optional: Add your custom domain to Cloudflare

3. **Required Tools**
   - Backblaze B2 CLI: `pip install b2` or `brew install b2-tools`
   - Wrangler CLI: `npm install -g wrangler`

## Step 1: Configure Backblaze B2

### Create a B2 Bucket

1. Log in to Backblaze B2 console
2. Create a new bucket:
   - **Bucket Name**: `photostream` (or your choice)
   - **Files in Bucket**: Public or Private (recommend Private with Worker)
   - **Object Lock**: Disabled
   - **Encryption**: Disabled (Cloudflare provides TLS)

### Generate Application Key

1. Go to "App Keys" in B2 console
2. Click "Add a New Application Key"
3. Configure:
   - **Name**: `photostream-deploy`
   - **Allow access to**: Your bucket only
   - **Type**: Read and Write
4. Save the **keyID** and **applicationKey** (shown once)

### Get Bucket Endpoint

Your B2 bucket endpoint follows this format:
```
https://YOUR-BUCKET-NAME.s3.us-west-004.backblazeb2.com
```

The region code may vary (us-west-004, us-east-005, eu-central-003, etc.)

Find your exact endpoint in the B2 console under bucket details.

## Step 2: Configure Environment Variables

Create a `.env` file in your project root:

```bash
# Backblaze B2 Configuration
export B2_BUCKET_NAME="photostream"
export B2_KEY_ID="your-key-id-here"
export B2_APPLICATION_KEY="your-application-key-here"
```

Add `.env` to your `.gitignore` to keep credentials safe:
```bash
echo ".env" >> .gitignore
```

Load environment variables:
```bash
source .env
```

## Step 3: Build Your Gallery

Build the static gallery files:

```bash
python3 build.py ./originals --out-dir ./site --preview-height 400 --workers 8
```

This creates the `./site` directory with your gallery.

## Step 4: Deploy to Backblaze B2

Run the deployment script:

```bash
./deploy-b2.sh
```

The script will:
1. Verify B2 credentials and bucket access
2. Sync all files from `./site` to your B2 bucket
3. Set appropriate content-type headers
4. Remove old files that no longer exist locally

### Manual Deployment (Alternative)

If you prefer manual control:

```bash
# Authorize
b2 account authorize $B2_KEY_ID $B2_APPLICATION_KEY

# Sync files
b2 sync --delete --replaceNewer --threads 10 ./site b2://photostream

# Check uploaded files
b2 ls --recursive photostream
```

## Step 5: Configure Cloudflare Worker

### Create Cloudflare Configuration Files

First, create the `cloudflare/` directory with the necessary files:

```bash
mkdir -p cloudflare
cp cloudflare/worker.js.example cloudflare/worker.js
cp cloudflare/wrangler.toml.example cloudflare/wrangler.toml
```

Note: The `cloudflare/` directory is in `.gitignore` to prevent accidentally committing credentials.

### Update Worker Configuration

1. Edit `cloudflare/worker.js` and set your B2 bucket endpoint:

```javascript
const B2_BUCKET_ENDPOINT = 'photostream.s3.us-west-004.backblazeb2.com'
```

2. Edit `cloudflare/wrangler.toml` with your Cloudflare details:

```toml
name = "photostream"
main = "worker.js"
compatibility_date = "2025-01-01"

# Add your account ID from Cloudflare dashboard
account_id = "your-account-id-here"

# For testing on workers.dev subdomain
workers_dev = true

# OR for custom domain:
# routes = [
#   { pattern = "photos.example.com/*", zone_name = "example.com" }
# ]
```

### Deploy the Worker

```bash
# Navigate to cloudflare directory
cd cloudflare

# Login to Cloudflare (first time only)
wrangler login

# Deploy the worker
wrangler deploy

# Return to project root
cd ..
```

Wrangler will output your worker URL, e.g.:
```
https://photostream.your-subdomain.workers.dev
```

## Step 6: Test Your Gallery

Visit your worker URL and verify:
- ✓ Main gallery page loads
- ✓ Images display correctly
- ✓ Individual photo pages work
- ✓ Navigation functions properly

Check caching headers:
```bash
curl -I https://photostream.your-subdomain.workers.dev/
```

Look for `X-Cache-Status: HIT` on subsequent requests.

## Step 7: Custom Domain (Optional)

### Add Custom Domain to Worker

1. In Cloudflare dashboard, go to Workers & Pages
2. Select your worker
3. Click "Triggers" → "Add Custom Domain"
4. Enter your domain (e.g., `photos.example.com`)
5. Cloudflare will automatically configure DNS

Alternatively, update `cloudflare/wrangler.toml`:

```toml
routes = [
  { pattern = "photos.example.com/*", zone_name = "example.com" }
]
```

Then redeploy:
```bash
cd cloudflare && wrangler deploy && cd ..
```

## Updating Your Gallery

Whenever you add new photos:

1. **Build**: `python3 build.py ./originals --out-dir ./site`
2. **Deploy**: `./deploy-b2.sh`
3. **Purge Cache** (optional): `wrangler pages deployment tail` or wait for cache expiry

The Cloudflare Worker caches HTML for 1 hour and images for 1 year, so new content may take up to 1 hour to appear.

### Force Cache Purge

To immediately update cached content:

```bash
# Purge everything (not recommended for production)
curl -X POST "https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache" \
  -H "Authorization: Bearer {api_token}" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything":true}'
```

Or use Cloudflare dashboard: Caching → Configuration → Purge Cache

## Cost Estimate

### Backblaze B2
- **Storage**: $6/TB/month (first 10GB free)
- **Download**: $0.01/GB (first 1GB/day free)
- **API calls**: Free for most operations

Example: 50GB gallery with 10GB/month traffic = ~$0.30/month

### Cloudflare Workers
- **Free tier**: 100,000 requests/day
- **Paid**: $5/month for 10M requests + $0.50 per additional million

Example: Small personal gallery = FREE

## Troubleshooting

### Images not loading

1. Check B2 bucket is public or Worker has proper authentication
2. Verify B2_BUCKET_ENDPOINT in worker.js matches your bucket
3. Check browser console for CORS errors

### 404 errors

1. Ensure files were uploaded: `b2 ls --recursive photostream`
2. Check path mapping in worker.js
3. Verify index.html exists in bucket root

### Cache not working

1. Check `X-Cache-Status` header in response
2. Wait for cache warmup (first request is always MISS)
3. Verify Cloudflare caching is enabled in dashboard

### Deployment fails

1. Verify B2 credentials: `b2 account get`
2. Check bucket name matches environment variable
3. Ensure b2 CLI is up to date: `pip install --upgrade b2`

## Security Best Practices

1. **Never commit credentials**: Keep `.env` in `.gitignore`
2. **Use application keys**: Don't use master key for deployment
3. **Restrict bucket access**: Create key with minimal permissions
4. **Enable HTTPS**: Cloudflare automatically provides TLS
5. **Private buckets**: Use private B2 buckets with Worker proxy

## Advanced Configuration

### Adding Authentication

Edit `cloudflare/worker.js` to add basic auth:

```javascript
const ADMIN_USER = 'admin'
const ADMIN_PASS = 'your-secure-password'

function checkAuth(request) {
  const auth = request.headers.get('Authorization')
  if (!auth || !auth.startsWith('Basic ')) return false

  const [user, pass] = atob(auth.slice(6)).split(':')
  return user === ADMIN_USER && pass === ADMIN_PASS
}

// In handleRequest:
if (!checkAuth(request)) {
  return new Response('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Photostream"' }
  })
}
```

### Custom Cache Rules

Adjust cache TTL in `cloudflare/worker.js`:

```javascript
if (contentType.includes('text/html')) {
  response.headers.set('Cache-Control', 'public, max-age=300') // 5 minutes
} else if (contentType.includes('image/')) {
  response.headers.set('Cache-Control', 'public, max-age=31536000, immutable') // 1 year
}
```

## Additional Resources

- [Backblaze B2 Documentation](https://www.backblaze.com/docs/cloud-storage)
- [Cloudflare Workers Documentation](https://developers.cloudflare.com/workers/)
- [Wrangler CLI Reference](https://developers.cloudflare.com/workers/wrangler/)
