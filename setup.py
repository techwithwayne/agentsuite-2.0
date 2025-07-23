from setuptools import setup, find_packages

setup(
    name="webdoctor",
    version="0.1.0",
    packages=find_packages(include=["webdoctor", "webdoctor.*"]),
    include_package_data=True,
    install_requires=[
        "Django>=3.2",
    ],
    author="Wayne",
    author_email="support@techwithwayne.com",
    description="AI-powered multilingual website diagnostic support widget for Django.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://techwithwayne.com",
    license="MIT",
    classifiers=[
        "Framework :: Django",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License"
    ],
    python_requires='>=3.6',
)
