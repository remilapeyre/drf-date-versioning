from setuptools import setup


setup(name="drf-date-versioning",
      version="0.0.1",
      description="API versioning by date for Django Rest Framework",
      author="Remi Lapeyre",
      author_email="remi.lapeyre-ext@johnpaul.com",
      license="GPL-2.0",
      install_requires=[
          "django",
          "djangorestframework"
      ],
      packages=["date_versioning"],
)
