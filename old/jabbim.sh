#!/bin/sh
dir_name="$0"
if [ -L "$dir_name" ]; then
  dir_name=`readlink "$dir_name"`
fi
dir_name=`dirname "$dir_name"`
cd "$dir_name/src"

exec python -OO jabbim.py $@
