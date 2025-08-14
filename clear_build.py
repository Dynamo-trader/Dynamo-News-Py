import os
import shutil


def clear_build():
    shutil.rmtree("dist", ignore_errors=True)
    shutil.rmtree("dynamo_news.egg-info", ignore_errors=True)

    path = "dynamo_news"
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith((".so", ".c", ".pyc", ".pyd", ".pyc")):
                print(file)
                os.remove(os.path.join(root, file))


if __name__ == "__main__":
    clear_build()
