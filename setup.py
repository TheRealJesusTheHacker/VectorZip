from setuptools import setup

setup(
    name="vectorzip-py",
    version="1.2.9",
    description="A lossless, chunked-processing compression utility.",
    author="VectorZip Developer",
    packages=["vectorzip", "gui"],
    package_dir={"vectorzip": "src", "gui": "gui"},
    py_modules=["main", "gui_launcher"],
    install_requires=[
        "tqdm==4.70.1",
    ],
    extras_require={
        # The GUI (gui_launcher / vectorzip-gui) needs PyQt6; the CLI and
        # the codec library do not, so CLI-only installs no longer have
        # to pull in the full Qt stack. Install with: pip install .[gui]
        "gui": ["PyQt6==6.11.0"],
    },
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
