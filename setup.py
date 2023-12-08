from setuptools import setup

setup(
    name="aiproxy-python",
    version="0.2.0",
    url="https://github.com/uezo/aiproxy",
    author="uezo",
    author_email="uezo@uezo.net",
    maintainer="uezo",
    maintainer_email="uezo@uezo.net",
    description="🦉AIProxy is a reverse proxy for ChatGPT API that provides monitoring, logging, and filtering requests and responses.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    install_requires=[
        "openai==1.3.6",
        "fastapi==0.103.2",
        "uvicorn==0.23.2",
        "sse-starlette==1.8.2",
        "tiktoken==0.5.1",
        "SQLAlchemy==2.0.23"
    ],
    license="Apache v2",
    packages=["aiproxy"],
    classifiers=[
        "Programming Language :: Python :: 3"
    ]
)
