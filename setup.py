from setuptools import setup

setup(
    name="VectorZip",
    version="1.0.0",
    description="A lossless, chunked-processing compression utility.",
    author="VectorZip Developer",
    packages=["vectorzip"],
    package_dir={"vectorzip": "src"},
    py_modules=["main"],
    install_requires=[
        "tqdm>=4.60.0",
    ],
    entry_points={
        'console_scripts': [
            'vzip=main:main',
        ],
    },
    python_requires='>=3.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Operating System :: OS Independent",
    ],
)
