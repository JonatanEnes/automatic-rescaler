DEV_PATH=$HOME/development
RESCALER_PATH=$DEV_PATH/automatic-rescaler
BDWACHDOG_PATH=$DEV_PATH/metrics-to-time-series
export PYTHONPATH=$RESCALER_PATH:$BDWACHDOG_PATH

tmux new -d -s "NodeRescaler" "python NodeRescaler/NodeRescaler.py"