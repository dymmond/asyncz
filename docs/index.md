# Asyncz

<p align="center">
  <a href="https://asyncz.dymmond.com"><img src="https://res.cloudinary.com/dymmond/image/upload/v1667408187/asyncz/asyncz-logo_ox0ovh.png" alt='Asyncz'></a>
</p>

<p align="center">
    <em>🚀 The scheduler that simply works. 🚀</em>
</p>

<p align="center">
<a href="https://github.com/dymmond/asyncz/workflows/Test%20Suite/badge.svg?event=push&branch=main" target="_blank">
    <img src="https://github.com/dymmond/asyncz/workflows/Test%20Suite/badge.svg?event=push&branch=main" alt="Test Suite">
</a>

<a href="https://pypi.org/project/asyncz" target="_blank">
    <img src="https://img.shields.io/pypi/v/asyncz?color=%2334D058&label=pypi%20package" alt="Package version">
</a>

<a href="https://pypi.org/project/asyncz" target="_blank">
    <img src="https://img.shields.io/pypi/pyversions/asyncz.svg?color=%2334D058" alt="Supported Python versions">
</a>
</p>

---

**Documentation**: [https://asyncz.dymmond.com](https://asyncz.dymmond.com) 📚

**Source Code**: [https://github.com/dymmond/asyncz](https://github.com/dymmond/asyncz)

---

Asyncz is a scheduler for any ASGI application that needs to have those complicated scheduled operations with the
best of what pydantic can offer.

## Motivation

Nowadays using async frameworks with python is somewhat common and becoming even more mainstream. A lot of applications
usually need a complex stack of technologies to fullfil their needs and directly or indirectly, a scheduler.

There are great frameworks out there that do the job extremely well, the bet example is APScheduler, which is where
Asyncz is inspired by.

To be even more honest, Asyncz is a revamp of APScheduler. Without the APScheduler there is no Asyncz.

## Requirements

* Python 3.7+

Asyncz wouldn't be possible without two giants:

* <a href="https://apscheduler.readthedocs.io/en/3.x/" class="external-link" target="_blank">APScheduler</a>
* <a href="https://pydantic-docs.helpmanual.io/" class="external-link" target="_blank">Pydantic</a>


## Installation

```shell
$ pip install asyncz
```
