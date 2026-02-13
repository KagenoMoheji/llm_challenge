#!/bin/bash
#######################################################################################
# ●コマンド説明
# Dockerイメージをビルド＆コンテナ起動する．
# 
# ●例
# $ sh dcup.bash
# $ sh dcup.bash -s dev
#
# - MEMO
#   - `docker-compose.yml`で`user: ${UID_HOST}:${GID_HOST}`して本bashを実行してみたところ，ホストのUIDで入って操作できそうだが，コンテナ内でのユーザ名が"i have no name!"になってしまう．
#       - コンテナビルド時にユーザ名を変更することを試そうとしたが古いユーザ名を得づらいかもしれないのと，ユーザディレクトリの改名も別途しないといけないかもしれないということで諦めた．
#   - `.env`で`USER_HOST=$(whoami)`とかしてみたが，コマンドの結果ではなくコマンド自体が代入されていて失敗．
#   - ホストの`/etc/passwd`と`/etc/group`をイメージ・コンテナにro(リードオンリー)でマウントさせる方法あったけど，ホストのユーザ情報全部をイメージ・コンテナに渡すって怖くない？そうでもないのか？
# - CONCLUSION
#   1. `docker-compose.yml`から`Dockerfile`にユーザ名・UID・GIDを渡すための引数定義をそれぞれのファイルで行う
#   2. `Dockerfile`にてユーザ名・UID・GIDを使ってグループ・ユーザを新規追加するコマンドを追加
#   3. 本bashのようにユーザ名・UID・GIDをexportした直後にdocker-composeするコマンドを実行してビルド
#   4. `docker exec -u $(id -u) -it {コンテナ名} bash`でroot以外のユーザでコンテナに入る
# - REFS
#   - [Set current host user for docker container](https://faun.pub/set-current-host-user-for-docker-container-4e521cef9ffc)
#   - [Running a Docker container as a non-root user](https://medium.com/redbubble/running-a-docker-container-as-a-non-root-user-7d2e00f8ee15)
#   - [Dockerコンテナに一般ユーザーを追加するときのDockerfileの設定](https://qiita.com/Spritaro/items/602118d946a4383bd2bb)
#   - [Dockerで実行ユーザーとグループを指定する](https://qiita.com/acro5piano/items/8cd987253cb205cefbb5)
#   - [Docker コンテナ内で Docker ホストと同じユーザを使う](https://blog.amedama.jp/entry/docker-container-host-same-user)
########################################################################################


export USER_HOST=$(whoami)
# export UID_HOST=$(id -u) # WSLのユーザが基本的にUID=1000だが、dockerコンテナ上でubuntuユーザのUIDが1000でコンフリクトするようになったので以下の方式に変更。
export UID_HOST=$(($(id -u)*3))
# export GID_HOST=$(id -g) # WSLのユーザが基本的にUID=1000だが、dockerコンテナ上でubuntuユーザのUIDが1000でコンフリクトするようになったので以下の方式に変更。
export GID_HOST=$(($(id -u)*3))
service_name=""
# コマンドライン引数を取得
while [ $# -gt 0 ]; do
    case $1 in
        -s)
            shift
            if [ ! -z $1 ]; then
                service_name=$1
            fi
            ;;
        *)
            ;;
    esac
    shift
done
echo ${service_name}

docker-compose up -d ${service_name}
