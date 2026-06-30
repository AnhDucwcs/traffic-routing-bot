$CurrentBranch = git branch --show-current

git branch -D hf-temp 2>$null

git checkout --orphan hf-temp

git rm -rf --cached . 2>$null

git add .
git add -f data\hcmc_routing_brain_v2.pkl
git add -f data\turn_penalties.pkl
git add -f data\hcmc_geometry_store.feather
git add -f data\master_stops.json
git add -f data\route_stop_sequence.json
git add -f data\segment_lengths_v2.json

git commit -m "Deploy to HuggingFace"

git push hf hf-temp:main --force

git checkout $CurrentBranch

git branch -D hf-temp