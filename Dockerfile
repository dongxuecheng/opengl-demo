FROM nvidia/cuda:13.0.2-runtime-ubuntu24.04

# 2. 环境变量设置
ENV DEBIAN_FRONTEND=noninteractive
# 设置虚拟环境路径
ENV VIRTUAL_ENV=/opt/venv
# 将虚拟环境的 bin 加入 PATH，确保后续直接输入 python/pip 调用的都是虚拟环境里的
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 3. 替换清华源 (适配 Ubuntu 24.04 的 DEB822 新格式)
# Ubuntu 24.04 的源文件位置变了，且内容格式也变了
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
    && sed -i 's|http://security.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources

# 4. 安装系统依赖
# python3-venv: Ubuntu 24.04 必须安装这个才能创建虚拟环境
# ffmpeg: 24.04 源里的 ffmpeg 版本通常是 6.x，对 NVENC 支持很好
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    libgl1 \
    libegl1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# 5. 创建并激活 Python 虚拟环境 (解决 PEP 668 EXTERNALLY-MANAGED 报错)
RUN python3 -m venv $VIRTUAL_ENV

# 6. 安装 Python 库 (安装在虚拟环境中)
# moderngl: 核心库
# ffmpeg-python: 管道操作
# numpy: 数学计算
# --no-cache-dir 减小镜像体积
RUN pip install \
    -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    moderngl \
    ffmpeg-python \
    numpy \
    pyglm \
    Pillow \
    PyYAML \
    -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
# 7. 设置工作目录
WORKDIR /app
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && \
    echo '{"file_format_version" : "1.0.0", "ICD" : {"library_path" : "libEGL_nvidia.so.0"}}' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
# 8. 验证环境 (可选)
# 打印一下版本信息确保安装成功
RUN python -c "import moderngl; print(f'ModernGL Version: {moderngl.__version__}')"

CMD ["python"]