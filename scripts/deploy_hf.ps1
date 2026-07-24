$CurrentBranch = git branch --show-current

Write-Host "Backing up data directory..."
if (Test-Path .data_backup) { Remove-Item -Recurse -Force .data_backup }
New-Item -ItemType Directory -Force -Path .data_backup | Out-Null
Copy-Item -Path data\* -Destination .data_backup -Recurse

git branch -D hf-temp 2>$null

git checkout --orphan hf-temp

git rm -rf --cached . 2>$null

Add-Content .gitignore "`n*.png`n*.jpg`n*.jpeg`n.data_backup/" -ErrorAction SilentlyContinue

git add .
git add -f data\hcmc_routing_brain_v2.pkl
git add -f data\turn_penalties.pkl
git add -f data\hcmc_geometry_store.feather
git add -f data\master_stops.json
git add -f data\route_stop_sequence.json
git add -f data\segment_lengths_v2.json
git add -f data\edge_index.npy
git add -f data\id_to_edge.pkl
git add -f data\stgcn_best.pth

git commit -m "Deploy to HuggingFace"

git push hf hf-temp:main --force

git checkout $CurrentBranch

Write-Host "Restoring data directory..."
Copy-Item -Path .data_backup\* -Destination data -Recurse -Force
Remove-Item -Recurse -Force .data_backup

git branch -D hf-temp