"""Выполняет все ячейки ноутбука в IPython без сетевого Jupyter-ядра."""

import os
from pathlib import Path
import sys

from IPython.core.interactiveshell import InteractiveShell
from IPython.utils.capture import capture_output
import nbformat


def main():
    root = Path(__file__).resolve().parents[1]
    notebook = nbformat.read(root / 'analytics/analysis.ipynb', as_version=4)
    nbformat.validate(notebook)
    cells = [cell for cell in notebook.cells if cell.cell_type == 'code']
    original_directory, original_path = Path.cwd(), sys.path[:]
    shell = InteractiveShell.instance()
    try:
        sys.path.insert(0, str(root))
        for directory in (root, root / 'analytics'):
            os.chdir(directory)
            shell.reset(new_session=False)
            for run in (1, 2):
                for index, cell in enumerate(cells, start=1):
                    with capture_output():
                        result = shell.run_cell(cell.source)
                    if not result.success:
                        raise RuntimeError(f'Ошибка ячейки {index}, запуск {run}, каталог {directory.name}') from (
                            result.error_before_exec or result.error_in_exec
                        )
                print(f'OK: {directory.name}, запуск {run}, выполнено ячеек: {len(cells)}')
    finally:
        os.chdir(original_directory)
        sys.path[:] = original_path
        shell.reset(new_session=False)


if __name__ == '__main__':
    main()
