from starlette.templating import Jinja2Templates

from app.utils.path_utils import PROJECT_ROOT

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
