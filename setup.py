from setuptools import setup

setup(
    name="VectorZip",
    version="1.2.0",
    description="A lossless, chunked-processing compression utility.",
    author="VectorZip Developer",
    packages=["vectorzip", "gui"],
    package_dir={"vectorzip": "src", "gui": "gui"},
    py_modules=["main", "gui_launcher"],
    install_requires=[
        "tqdm>=4.60.0",
        "PyQt6>=6.5.0",
    ],
    entry_points={
        'console_scripts': [
            'vzip=main:main',
            'vectorzip-gui=gui_launcher:main',
        ],
    },
    python_requires='>=3.8',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
        "Operating System :: OS Independent",
    ],
)
