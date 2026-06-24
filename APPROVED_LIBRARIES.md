# Approved Python Libraries — bank env (Python 3.11)

Authoritative list of Python libraries available in the target deployment
environment inside the bank. Mirrored verbatim in `cjipro/mil_streamlit`
(`while-sleeping`) — drift between the two copies is a bug.

## The rule

**Any new Python dependency added to this repo MUST be on this list.**

If a library you want isn't on the list:

1. Check this list for a substitute that fits — almost always one exists.
2. If no substitute exists, file a Jira ticket (PULSE / HOL as appropriate)
   proposing the library + justification + procurement/security risk.
   Do not add it until ratified.
3. Update this list (and the while-sleeping mirror) when the bank env
   itself adds the package.

Scope: this constraint applies to all CJI / Pulse / MIL / Holter engine +
UI code intended to run inside the bank. Sister concerns that run
*outside* the bank (TAQ App on Cloudflare, hosted-reference instances on
cjipro.com, OSS Hodos reference deployments) have their own dependency
boundaries and are not bound by this list.

## Python version

**Python 3.11.x** (locked 2026-05-17 per HOL-1 framework decision input).

Pin in `pyproject.toml`:

```toml
[project]
requires-python = ">=3.11,<3.12"
```

## Source

Snapshot of `pip list` in the target bank env, shared 2026-05-17 via OCR
relay of an Excel screenshot. **Partial** — see Gaps below. Replace with a
direct `pip list > approved_packages.txt` dump from the bank env when
available; that becomes the canonical text and OCR notes can be deleted.

## Approved packages (alphabetical, pip-freeze format)

Notes on the OCR-extracted list:
- A handful of entries have OCR-suspect names — flagged inline with
  `# OCR?` and the most likely correct spelling. Treat the package as
  **probably present** but verify against a real `pip list` dump.
- Packages with no version shown left as `name` only.
- Internal bank packages anonymised per the `real_bank` naming-discipline
  lock — see "Bank-internal packages" section below.

```
aiobotocore==2.12.3                          # OCR showed "alobotocore"
aiohappyeyeballs==2.4.0
aiohttp==3.10.5
aioitertools==0.7.1
aiosignal==1.2.0
alabaster==0.7.16
alembic==1.14.1
altair==5.5.0
anaconda-anon-usage==0.4.4
anaconda-catalogs==0.2.0
anaconda-client==1.12.0
anaconda-cloud-auth==0.5.1
anaconda-navigator==2.6.2
anaconda-project==0.11.1
annotated-doc
annotated-types==0.6.0
anyio==4.2.0
appdirs==1.4.4
archspec==0.2.3
argon2-cffi==21.3.0
argon2-cffi-bindings==21.2.0
arrow==1.2.3
arviz==0.17.1
astroid==2.14.2
astropy==6.1.3
astropy-iers-data==0.2024.9.2.0.33.23
asttokens==2.0.5
async-lru==2.0.4
atomicwrites==1.4.0
attrs==23.1.0
autopep8==2.0.4
Babel==2.11.0
backports.functools-lru-cache==1.6.4
backports.tempfile==1.0
backports.weakref==1.0.post1
bash_kernel==0.10.0
bcrypt==3.2.0
beautifulsoup4==4.12.3
bertopic==0.16.1
binaryornot==0.4.4
black==24.8.0
bleach==4.1.0
blinker==1.6.2
blis==1.1.0
bokeh==3.4.1
boltons==23.0.0
botocore==1.34.69
Bottleneck==1.3.7
Brotli==1.0.9
bump2version==1.0.1
ca_core_news_lg==3.8.0
cachetools==5.5.2
catalogue==2.0.10
certifi==2025.1.31
cffi==1.17.1
cfgv==3.4.0
chardet==4.0.0
charset-normalizer==3.3.2
click==8.1.7
cloudpathlib==0.20.0
cloudpickle==3.0.0
colorama==0.4.6
colorcet==3.1.0
comm==0.2.1
conda==24.11.3
conda-build==24.9.0
conda-content-trust==0+unknown
conda_index==0.5.0
conda-libmamba-solver==24.7.0
conda-pack==0.6.0
conda-package-handling==2.2.0
conda_package_streaming==0.9.0
conda-repo-cli==1.0.88
conda-token==0.4.0
conda-verify==3.4.2
confection==0.1.5
constantly==23.10.4
contourpy==1.2.0
cookiecutter==2.6.0
coverage==7.6.7
cryptography==43.0.0
cssselect==1.2.0
curio==1.6
cycler==0.11.0
cymem==2.0.10
Cython==0.29.37
cytoolz==0.12.2
daal4py==2023.1.1
dask-expr==1.1.21
dask-glm==0.3.2
dask-ml==2024.4.4
databricks-sdk==0.44.1
datasets==2.19.1
datashader==0.16.3
debugpy==1.6.7
decorator==5.1.1
defusedxml==0.7.1
Deprecated==1.2.18
diff-match-patch==20200713
dill==0.3.8
distlib==0.3.9
distributed==2024.12.1
distro==1.9.0
docker==7.1.0
docrepr==0.2.0
docstring-to-markdown==0.11
docutils==0.18.1
duckdb==1.5.2  # PULSE-130: confirmed on edge node 2026-05-23 (superseded the 2026-05-20 provisional ~1.1.x guess)
en_core_web_sm==3.8.0
entrypoints==0.4
et_xmlfile==1.1.0
exceptiongroup==1.2.2
executing==0.8.3
fastapi==0.136.1
fastjsonschema==2.16.2
filelock==3.13.1
filetype==1.2.0
findspark==2.0.1
flake8==7.0.0
Flask==3.0.3
fonttools==4.51.0
frozendict==2.4.2
frozenlist==1.4.0
fsspec==2024.3.1
future==0.18.3
fuzzywuzzy==0.18.0
gensim==4.3.3
gitdb==4.0.12
GitPython==3.1.44
grpc2==2.1.2                                 # OCR? likely grpcio
google-auth==2.38.0
graphene==3.4.3
graphql-core==3.2.6
graphql-relay==3.2.0
greenlet==3.0.1
gunicorn==23.0.0
h11==0.14.0
h5netcdf==1.2.0
h5py==3.11.0
HaapDict==1.0.1                              # OCR? likely HeapDict
holoviews==1.19.1
httpcore==1.0.2
httpx==0.27.0
huggingface_hub==0.24.6
hvplot==0.10.0
hyperlink==21.0.0
hypothesis==6.127.9
identify==2.6.2
idna==3.7
imagecodecs==2023.1.23
imageio==2.33.1
imagesize==1.4.1
imbalanced-learn==0.12.3
importlib-metadata==7.0.1
incremental==22.10.0
inflection==0.5.1
iniconfg==1.1.1                              # OCR? likely iniconfig
intake==2.0.7
intersphinx_registry==0.2501.23
intervaltree==3.1.0
ipykernel==6.28.0
ipython==9.0.1
ipython-genutils==0.2.0
ipython_pygments_lexers==1.1.1
ipywidgets==8.1.2
isort==5.13.2
itemadapter==0.3.0
itemloaders==1.1.0
itsdangerous==2.2.0
jaraco.classes==3.2.1
jedi==0.19.1
jeepney==0.7.1
jellyfish==0.11.2                            # OCR partial
Jinja2==3.1.4                                # PULSE-94: confirmed in bank env 2026-05-23 (py3.11 anaconda); Flask 3.0.3 transitive dep — closes an OCR gap, not a new dep
joblib==1.4.2
json5==0.9.6
jsonpatch==1.33
jsonpointer==2.1
jsonschema==4.19.2
jsonschema-specifications==2023.7.1
jupyter==1.0.0
jupyter_client==7.4.9
jupyter-console==6.6.3
jupyter_contrib_core==0.4.2
jupyter_core==5.7.2
jupyter-highlight-selected-word==0.2.0
jupyter-lsp==2.2.0
jupyter_nbextensions_configurator==0.5.4
jupyter_server==2.14.1
jupyter-server-mathjax
jupyter_server_proxy
jupyter_server_terminals
jupyterlab==4.2.5
jupyterlab_git
jupyterlab-pygments
jupyterlab_server
jupyterlab-spreadsheet
jupyterlab-spreadsheet-editor
jupyterlab-widgets
keyring
kiwisolver==1.4.4
langcodes
language_data
lazy_loader
lazy-object-proxy
libarchive-c==5.1
libmambapy==4.5.8
linkify-it-py==1.0
lmdb
locket==1.0.0
lxml==4.8.0
Mako
marisa-trie
Markdown
markdown-it-py
MarkupSafe
matplotlib

# --- GAP: m-n range (mistune, mkl*, multidict, mypy, nbclient,
#     nbconvert, nbformat, nest-asyncio, networkx, nltk, etc.) ---

notebook==6.5.7
notebook_shim==0.2.3
numba==0.60.0
numexpr==2.8.7
numpy==1.26.4
numpydoc==1.7.0
nvidia-cublas-cu12==12.4.5.8
nvidia-cuda-cupti-cu12==12.4.1
nvidia-cuda-nvrtc-cu12==12.4.1
nvidia-cuda-runtime-cu12==12.4
nvidia-cudnn-cu12==9.1.0.70
nvidia-cufft-cu12==11.2.1.3
nvidia-curand-cu12==10.3.5.1
nvidia-cusolver-cu12==11.6.1.5
nvidia-cusparse-cu12==12.3.1
nvidia-nccl-cu12==2.21.5
nvidia-nvjitlink-cu12==12.4.127
nvidia-nvtx-cu12==12.4.127
openpyxl==3.1.5
opentelemetry-api==1.30.0
opentelemetry-sdk==1.30.0
opentelemetry-semantic-conventions
outcome==1.3.0.post0
overrides==7.4.0
packaging==24.1
pandas==2.2.3
pandocfilters==1.5.0
panel==1.4.4
param==2.1.1
parsel==1.8.1
parso==0.8.3
partd==1.4.1
pathspec==0.10.3
patsy==0.5.6
pep8==1.7.1
pexpect==4.8.0
pickleshare==0.7.5
pillow==10.4.0
pip==26.0.1
pkce==1.0.3
pkginfo==1.10.0
platformdirs==3.10.0
plotly==5.24.1
pluggy==1.0.0
ply==3.11
polars==1.34.0
polars-runtime-32==1.34.0
pre_commit==4.0.1
preshed==3.0.9
prometheus-client==0.14.1
prompt-toolkit==3.0.43
Protego==0.1.16
protobuf==5.29.3
psutil==5.9.0
ptyprocess==0.7.0
pure-eval==0.2.2
py-cpuinfo==9.0.0
py4j==0.10.7
pyarrow==18.1.0
pyasn1==0.4.8
pyasn1-modules==0.2.8
pycodestyle==2.11.1
pycosat==0.6.6
pycparser==2.21
pyct==0.5.0
pycurl==7.45.3
pydantic==2.13.4
pydantic_core==2.46.4
pydeck==0.9.1
PyDispatcher==2.0.5
pydocstyle==6.3.0
pyerfa==2.0.1.4
pyflakes==3.2.0
Pygments==2.15.1
PyJWT==2.8.0
pylint==2.16.2
pylint-venv==3.0.3
pyls-spyder==0.4.0
pynndescent==0.5.13
pyodbc==5.1.0
pyOpenSSL==24.2.1
pypandoc==1.5
pyparsing==3.1.2
PyQt5==5.15.10
PyQt5-sip==12.13.0
PyQtWebEngine==5.15.6
PySocks==1.7.1
pyspark==2.4.0
pytest==7.4.4
pytest-asyncio==0.21.2
pytest-cov==6.0.0
pytest-mock==3.14.0
python-dateutil==2.9.0.post0
python-dotenv==0.21.0
python-json-logger==2.0.7
python-lsp-black==2.0.0
python-lsp-jsonrpc==1.1.2
python-lsp-server==1.10.0
python-slugify==5.0.2
pytoolconfig==1.2.6
pytz==2024.1
pyviz_comms==3.0.2
PyWavelets==1.7.0
pyxdg==0.27
PyYAML==6.0.1
pyzmq==25.1.2
QDarkStyle==3.2.3
qstylizer==0.2.2
QtAwesome==1.3.1
qtconsole==5.5.1
QtPy==2.4.1
queuelib==1.6.2
RapidFuzz==3.13.0
referencing==0.30.2
regex==2024.9.11
requests==2.32.3
requests-file==1.5.1
requests-toolbelt==1.0.0
rfc3339-validator==0.1.4
rfc3986-validator==0.1.1
rich==13.7.1
rope==1.12.0
rpds-py==0.10.6
rsa==4.9
Rtree==1.0.1
ruamel.yaml==0.17.21
ruamel-yaml-conda==0.17.21
s3fs==2024.3.1
safetensors==0.4.4
scikit-image==0.24.0
scikit-learn==1.5.1
scikit-learn-intelex==20230426.111612
scipy==1.13.1
Scrapy==2.11.1
seaborn==0.13.2
SecretStorage==3.3.1
semver==3.0.2
Send2Trash==1.8.2
sentence-transformers==3.3.1
service-identity==18.1.0
setuptools==75.8.2
shellingham==1.5.4
simpervisor==1.0.0
sip==6.7.12
six==1.16.0
smart-open==5.2.1
smmap==5.0.2
sniffio==1.3.0
snowballstemmer==2.2.0
sortedcontainers==2.4.0
soupsieve==2.5
spacy==3.8.3
spacy-legacy==3.0.12
spacy-loggers==1.0.5
spacy-lookups-data==1.0.5
spark-nlp==5.5.2
sparse==0.15.5
Sphinx==7.3.7
sphinx-rtd-theme==3.0.2
sphinx_toml==0.0.4
sphinxcontrib-applehelp==1.0.2
sphinxcontrib-devhelp==1.0.2
sphinxcontrib-htmlhelp==2.0.0
sphinxcontrib-jquery==4.1
sphinxcontrib-jsmath==1.0.1
sphinxcontrib-qthelp==1.0.3
sphinxcontrib-serializinghtml==1.1.10
spyder==5.5.1
spyder-kernels==2.5.0
SQLAlchemy==2.0.34
sqlparse==0.5.3
srsly==2.5.0
stack-data==0.2.0
starlette==1.0.0
statsmodels==0.14.2
streamlit==1.46.0
sympy==1.13.1
tables==3.10.1
tabulate==0.9.0
TBB==0.2
tblib==1.7.0
tenacity==8.2.3
terminado==0.17.1
testpath==0.6.0
text-unidecode==1.3
textdistance==4.2.1
thinc==8.3.3
threadpoolctl==3.5.0
three-merge==0.1.1
tifffile==2023.4.12
tinycss2==1.2.1
tldextract==5.1.2
tokenizers  # PULSE-130: transformers 4.44.1 dep, present on edge node; exact pin pending pip-list dump
torch==2.5.0  # PULSE-130: +cu124 (GPU) build, confirmed on edge node 2026-05-23
transformers==4.44.1  # PULSE-130: confirmed on edge node 2026-05-23

# --- GAP: t-z range (tokenizers, tomli, tornado, tqdm, traitlets,
#     transformers, typer, typing-extensions, tzdata, urllib3, uvicorn,
#     virtualenv, watchdog, websockets, Werkzeug, wheel, xarray, xgboost,
#     yarl, zipp, zstandard, etc.) ---
```

## ML model weights (run via `sentence-transformers`)

These are model *weights* (not PyPI packages) loaded through the already-approved
`sentence-transformers`. Listed here so the retrieval stack's model choices are
governed alongside the package list. All run on CPU (TDR-crash mitigation).

| Model | Used by | Role | Notes |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | `mil/chat/retrievers/embedding.py` | Ask CJI Pro dense retrieval | MIL-183 — replaced the 2021-era `all-MiniLM-L6-v2`; 384-dim, CPU-friendly |
| `cross-encoder/ms-marco-MiniLM-L6-v2` | `mil/chat/rerank.py` | Ask CJI Pro cross-encoder reranker | MIL-182 — re-scores merged candidates into one comparable ordering |
| `all-MiniLM-L6-v2` | `mil/inference/rag.py` | CHRONICLE RAG matching | retained; `sim_threshold=0.30` calibrated to it. Swap deferred (recalibration) |

Model names are centralised in `mil/config/retrieval_models.py`. Bank-env note:
weights must be pre-staged into the offline HF cache for air-gapped nodes (no
runtime download); on the dev/OSS machine they fetch from the HF Hub on first use.

## Bank-internal packages (env-only, not on PyPI)

Per the `real_bank` naming-discipline lock, internal package names are
sanitised in this document. They are present in the bank env but cannot be
installed elsewhere — treat them as available *only* when running inside
the bank, and never reference them in OSS code paths.

| Sanitised name | Version | Likely purpose |
|---|---|---|
| `real_bank-ace-simply-read` | 0.1.1 | ACE platform read-side client |
| `real_bank-ace-simply-spark` | 0.0.3 | ACE platform Spark client |
| `cust_complaints` | 0.1.0 | Customer-complaints data access (likely internal) |

## Gaps

This snapshot is partial. Two alphabetical ranges are not yet captured:

- **m–n range** (between `matplotlib` and `notebook`) — includes likely
  presences: `matplotlib-inline`, `mccabe`, `mdurl`, `mistune`, `mkl*`,
  `mpmath`, `msgpack`, `multidict`, `mypy_extensions`, `nbclient`,
  `nbconvert`, `nbformat`, `nest-asyncio`, `networkx`, `nh3`, `nltk`,
  `nodeenv`, etc.
- **t–z range** (after `tldextract`) — `torch`, `transformers`, `tokenizers`
  now captured above (PULSE-130, edge node 2026-05-23). Other likely presences:
  `toml`, `tomli`, `tomli_w`, `tomlkit`, `toolz`,
  `tornado`, `tqdm`, `traitlets`, `typeguard`, `typer`,
  `typing-extensions`, `tzdata`, `uc-micro-py`, `ujson`, `unicodedata2`,
  `uri-template`, `urllib3`, `uvicorn`, `virtualenv`, `watchdog`,
  `wcwidth`, `webencodings`, `websocket-client`, `websockets`, `Werkzeug`,
  `wheel`, `widgetsnbextension`, `wrapt`, `xarray`, `xgboost`(?), `xlrd`,
  `yapf`, `yarl`, `zict`, `zipp`, `zstandard`.

Until those gaps close, when proposing a dependency in those ranges:
**confirm with Hussain (or against a fresh `pip list` dump) before
adding**. Until then they are not on this list and therefore not approved.

To close the gaps: in the bank env, run
`pip list --format=freeze > approved_packages.txt` and share the file.
Then replace the body of this document with the real output, delete the
OCR caveats, and remove this Gaps section.

## When to update this list

- New `pip list` dump shared from the bank env → replace body verbatim
  (sanitising internal package names per `real_bank` discipline).
- Bank env Python version changes → update the version lock above.
- Library audit findings (compliance / security concerns) → mark packages
  with `# STATUS: <note>` inline.
- A new library is ratified through ticket review → add to the list with
  the ticket number in a comment: `<package>==<version>  # PULSE-N`.

## Cross-repo mirror

This file is duplicated verbatim in two repos that share the bank-env
constraint:

- `cjipro/holter` (this file)
- `cjipro/mil_streamlit` — `C:\Users\hussa\while-sleeping\APPROVED_LIBRARIES.md`

Keep them in sync. Drift = bug. If editing one, edit the other in the
same logical change.
