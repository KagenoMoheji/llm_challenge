#!/bin/bash
#######################################################################################
# ●コマンド説明
# Dockerコンテナに入る．
# 
# ●例
# $ sh dexec.bash -u current -c all_ml_libs
# $ sh dexec.bash -u root -c all_ml_libs
########################################################################################


user_host=""
container_name=""
# コマンドライン引数を取得
while [ $# -gt 0 ]; do
    case $1 in
        -u)
            shift
            if [ $1 = "current" ]; then
                # user_host=$(id -u) # dcup.bashでの方針変更に合わせて以下に変更。
                user_host=$(($(id -u)*3))
            elif [ $1 = "root" ]; then
                user_host=$1
            fi
            ;;
        *)
            ;;
    esac
    case $1 in
        -c)
            shift
            container_name=$1
            ;;
        *)
            ;;
    esac
    shift
done

if [ -z ${user_host} ]; then
    echo "Invalid value in option '-u'."
    exit 1
fi
if [ -z ${container_name} ]; then
    echo "Option '-c' is required."
    exit 1
fi

docker exec -u ${user_host} -it ${container_name} bash