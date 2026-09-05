$ErrorActionPreference = "Stop"

$RemoteUser = "rama"
$RemoteIP = "100.100.89.45"
$RemoteDir = "/home/rama/rlt_project"
$LocalDir = $PSScriptRoot

Write-Host "Starting deployment to $RemoteIP as $RemoteUser..." -ForegroundColor Cyan

# 1. Create dir
Write-Host "[1/3] Creating directory on server..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} "mkdir -p $RemoteDir"

# 2. Copy files
Write-Host "[2/3] Copying files..." -ForegroundColor Yellow
$ItemsToCopy = @("dataset", "docs", "RLT_project", "scripts", "txt_dataset", "pipeline_instructions.md", "project_structure.md")

foreach ($item in $ItemsToCopy) {
    $itemPath = Join-Path $LocalDir $item
    if (Test-Path $itemPath) {
        Write-Host "Copying $item..."
        scp -r -o StrictHostKeyChecking=no "$itemPath" "${RemoteUser}@${RemoteIP}:${RemoteDir}/"
    }
}

# 3. Run on server
Write-Host "[3/3] Running tests on server..." -ForegroundColor Yellow
$RemoteCommand = @"
cd $RemoteDir
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip3 install transformers numpy tqdm qdrant-client sentence-transformers
python3 RLT_project/rag/index_knowledge_base.py --test
"@

ssh -o StrictHostKeyChecking=no ${RemoteUser}@${RemoteIP} $RemoteCommand

Write-Host "Done!" -ForegroundColor Green
