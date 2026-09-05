$ErrorActionPreference = "Stop"

$RemoteUser = "rama"
$RemoteIP = "100.100.89.45"
$RemoteDir = "/home/rama/rlt_project"

Write-Host "1. Uploading code archive..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no code_only.zip "${RemoteUser}@${RemoteIP}:${RemoteDir}/"

Write-Host "`n2. Updating server configuration and restarting containers..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
echo 'Extracting code...'
unzip -o code_only.zip

echo 'Fixing IPv6 networking issues (forcing IPv4)...'
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1
sudo sysctl -w net.ipv6.conf.lo.disable_ipv6=1

echo 'Fixing Docker daemon...'
sudo rm -f /etc/docker/daemon.json
sudo systemctl restart docker

echo 'Rebuilding and restarting Web container...'
sudo docker compose up --build -d
echo 'Containers are running! You can check logs with: sudo docker compose logs -f'
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "`nDone! Code updated and ML service is running." -ForegroundColor Green
