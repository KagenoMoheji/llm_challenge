FROM ubuntu:latest

ARG USER_HOST
ARG UID_HOST
ARG GID_HOST
ARG APPNAME
ARG SHARED_WORKSPACE_HOST
ARG SHARED_WORKSPACE_CONTAINER
ARG NODE_VERSION
# ARG PORT_WEBPACK_BUNDLE_ANALYZER
ENV NODEJS_HOME=/opt/nodejs

# NodeJSのインストール先にあらかじめ移動しておく
WORKDIR ${NODEJS_HOME}
# NodeJSインストールに必要な資材をコンテナに持ってくる
COPY ./docker/dev/tools /opt/docker/tools

# コンテナ内のユーザ管理の準備
RUN apt-get update \
    && apt-get install -y sudo \
    && groupadd -g ${GID_HOST} ${USER_HOST} \
    && useradd -m -s /bin/bash -u ${UID_HOST} -g ${GID_HOST} ${USER_HOST} \
    && echo "${USER_HOST} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers \
    # ユーザ作成後にユーザ環境変数を登録
    ## NodeJSのbinを"${NODEJS_HOME}/"下に配置させるので、環境変数に登録してコマンド有効になるようにしておく。
    ## 非rootではnpm installとかができなかったりする(nodeユーザなら行ける？)ので、rootにもNODEJS_HOMEのパス通しておく
    && sudo echo "export PATH=${NODEJS_HOME}/bin:$PATH" >> /root/.bashrc \
    && echo "export PATH=${NODEJS_HOME}/bin:$PATH" >> /home/$(id -un ${UID_HOST})/.bashrc

# USER ${UID_HOST} # これやらないでrootでインストールとかしても、root以外でそのインストールした諸々のCLIとか使えるっぽいので良いか…？


# 以下、サービス別のコンテナに個別実装
RUN apt-get update \
    && apt-get install -y \
        vim \
        wget \
        curl \
        xz-utils \
    # NodeJSインストール
    # 方法(1)：3つの数字からなるバージョンにも対応しているシェル。nodejs.orgからダウンロードしてる。
    && bash /opt/docker/tools/install_node_from_nodeorg.sh -v ${NODE_VERSION} -h ${NODEJS_HOME}
    # 方法(2)：1つの数字からなるバージョンにしか対応できないシェル。nodesourceのセットアップを使用している。
    # && bash /opt/docker/tools/install_node_from_nodesource.sh -v ${NODE_VERSION} -h ${NODEJS_HOME}
# RUN node --version && npm --version && ls -la


# 開発ディレクトリに移動しての処理
WORKDIR ${SHARED_WORKSPACE_CONTAINER}