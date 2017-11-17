import * as gulpWatch from 'gulp-watch';
import { join } from 'path';
import * as runSequence from 'run-sequence';
import { config } from '../config/config';

import { changeFileManager } from './code_change_tools';

if (process.platform === 'darwin') {
  try {
    require('fsevents');
  } catch (err) {
    throw new Error('Could not require fsevents, please execute `npm install` again.');
  }
}

/**
 * Watches the task with the given taskname.
 * @param {string} taskname - The name of the task.
 */
export function watch(taskname: string) {
  return function () {
    let paths: string[] = [
      ...config.SOURCE_ROOTS.map(root => join(root, '**')),
      ...config.TEMP_FILES.map(temp => '!' + temp) ];

    gulpWatch(paths, (e: any) => {
      changeFileManager.addFile(e.path);

      // Resolves issue in IntelliJ and other IDEs/text editors which save multiple files at once.
      // https://github.com/mgechev/angular-seed/issues/1615 for more details.
      setTimeout(() => {

        runSequence(taskname, () => {
          changeFileManager.clear();
        });

      }, 50);
    });
  };
}
