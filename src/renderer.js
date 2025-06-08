// src/renderer.js

let currentFolder = null;
let currentImagePaths = [];

const btnChooseFolder = document.getElementById('btnChooseFolder');
const txtFolderPath   = document.getElementById('txtFolderPath');
const btnSortPrompt   = document.getElementById('btnSortPrompt');
const btnSortConcept   = document.getElementById('btnSortConcept');
const gridContainer   = document.getElementById('thumbnail-grid');

// Modal elements
const promptModal = document.getElementById('promptModal');
const promptModalContent = document.getElementById('promptModalContent');
const promptInput = document.getElementById('promptInput');
const promptOk    = document.getElementById('promptOk');
const promptCancel = document.getElementById('promptCancel');
let isModalOpen = false;
/**
 * Returns a Promise that resolves to the user’s input string
 * when they click OK, or null if they click Cancel.
 *
 * Doesn't work on 2nd try, why?
 */
function showPrompt() {
  return new Promise((resolve) => {
    // Prevent multiple modals
    if (isModalOpen) {
      console.log('Modal already open, ignoring');
      return;
    }

    isModalOpen = true;
    console.log('showPrompt called');

    // Get the original input element and its parent
    const originalInput = document.getElementById('promptInput');
    const inputParent = originalInput.parentNode;

    // Create a completely new input element
    const newInput = document.createElement('input');
    newInput.id = 'promptInput';
    newInput.type = 'text';
    newInput.className = originalInput.className;
    newInput.placeholder = originalInput.placeholder || '';
    newInput.value = '';

    // Add visual styling to show focus states
    newInput.style.border = '2px solid #007acc';
    newInput.style.outline = 'none';
    //promptModalContent.style.border = '3px solid #ff8c00';

    // Replace the old input with the new one
    inputParent.replaceChild(newInput, originalInput);

    // Show modal
    promptModal.style.display = 'flex';

    // Focus the new input
    setTimeout(() => {
      newInput.focus();
      newInput.select(); // Also try to select
      console.log('New input focused and selected');
    }, 150);

    function globalKeyHandler(e) {
      // Only handle if modal is open and new input is focused
      if (!isModalOpen || document.activeElement !== newInput) return;

      console.log('Global key pressed:', e.key);

      if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        handleOk();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        handleCancel();
      } else if (e.key.length === 1) {
        // Handle single character input manually
        e.preventDefault();
        newInput.value += e.key;
        console.log('Manually added character, new value:', newInput.value);
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        newInput.value = newInput.value.slice(0, -1);
        console.log('Manually removed character, new value:', newInput.value);
      }
    }

    function handleOk() {
      const value = newInput.value.trim();
      cleanup();
      resolve(value);
    }

    function handleCancel() {
      cleanup();
      resolve(null);
    }

    function cleanup() {
      console.log('Cleaning up');
      isModalOpen = false;
      document.removeEventListener('keydown', globalKeyHandler);
      promptOk.removeEventListener('click', handleOk);
      promptCancel.removeEventListener('click', handleCancel);
      promptModal.style.display = 'none';
      // Remove the styling when cleaning up
      //promptModalContent.style.border = '';
    }

    // Add listeners
    document.addEventListener('keydown', globalKeyHandler);
    promptOk.addEventListener('click', handleOk);
    promptCancel.addEventListener('click', handleCancel);
  });
}
/**
 * Render the thumbnails in the given array of absolute image paths.
 * Clears the grid and re-populates in-order.
 */
function renderThumbnails(imagePaths) {
  if (typeof imagePaths === 'string') {
  try {
    const parsed = JSON.parse(imagePaths);
    if (parsed && Array.isArray(parsed.imagePaths)) {
      imagePaths = parsed.imagePaths;
    }
  } catch (e) {
    console.error('Failed to parse imagePaths string:', e);
  }
}
  gridContainer.innerHTML = ''; // Clear existing thumbnails
  imagePaths.forEach((absPath) => {
    const div = document.createElement('div');
    div.classList.add('thumb-container');
    const img = document.createElement('img');
    console.log("absPath: ",absPath)
    img.src = `file://${absPath}`;
    img.alt = '';
    div.appendChild(img);
    gridContainer.appendChild(div);
  });
}

/** “Choose Folder” button handler */
btnChooseFolder.addEventListener('click', async () => {
  const result = await window.electronAPI.openFolder();

  console.log(result,"res", JSON.parse(JSON.stringify(result)))
  if (result.canceled) {
    return;
  }
  currentFolder = result.folderPath;
  currentImagePaths = result.imagePaths;
  txtFolderPath.value = currentFolder;
  btnSortPrompt.disabled = currentImagePaths.length === 0;
  btnSortConcept.disabled = currentImagePaths.length === 0;
  renderThumbnails(currentImagePaths);
});

function normalizeSlashes(str) {
  let out = '';
  for (let i = 0; i < str.length; i++) {
    const c = str[i];
    if (c === '/') {
      const prev = i > 0 ? str[i - 1] : '';
      const next = i < str.length - 1 ? str[i + 1] : '';
      // only replace if neither neighbor is "\" or "/"
      if (prev !== '\\' && prev !== '/' && next !== '\\' && next !== '/') {
        out += '\\';
      } else {
        out += '/';
      }
    } else {
      out += c;
    }
  }
  return out;
}

/** “Sort by Prompt” button handler */
// src/renderer.js

btnSortPrompt.addEventListener('click', async () => {
  if (!currentFolder || currentImagePaths.length === 0) return;

  // Show our custom prompt modal instead of window.prompt()

  const promptText = await showPrompt();
  if (!promptText) {
    // User clicked “Cancel” or left it blank
    return;
  }

  btnSortPrompt.innerText = 'Sorting…';
  btnSortPrompt.disabled = true;

  try {
    const sortedPaths = await window.electronAPI.sortByPrompt({
      folderPath: currentFolder,
      imagePaths: currentImagePaths,
      prompt: promptText,
    });

    // If Python returned something unexpected, bail out
    if (!Array.isArray(sortedPaths)) {
      throw new Error('sortByPrompt did not return an array');
    }

    // Ask the user: do you want to rename the actual files on disk?
  const doRename = confirm('Sort complete. Rename files on disk?');
  if (doRename) {
    // 1) Ask main to rename on disk
    await window.electronAPI.applyRenames({
      folderPath: currentFolder,
      sortedPaths, // absolute paths in old order
    });

    // 2) Build the new absolute paths (stripping old numeric prefixes, applying new ones)
const MAX_NAME_LEN = 100; // maximum length for the “name only” portion

const renamedPaths = sortedPaths.map((oldPath, index) => {
  // 1) Normalize any forward‐slashes to backslashes
const normalized1 = oldPath.includes('/')
  ? oldPath.replace(/\//g, '\\')
  //? oldPath.replace(/\//g, '\\')
  : oldPath;

  const normalized = normalized1.replace(/\\\\\\\\/g, '\\');

  // 2) Find the last backslash
  const lastSlash = normalized.lastIndexOf('\\');
  const dir = normalized.slice(0, lastSlash + 1);       // e.g. "C:\Users\DLF\Pictures\…\hoToCo\"
  let filename = normalized.slice(lastSlash + 1);        // e.g. "05_VeryLongName…jpg"

  // 3) Strip any existing "NN_" prefix
  filename = filename.replace(/^\d+_/, '');             // e.g. "VeryLongName…jpg"

  // 4) Split off extension
  const dotIndex = filename.lastIndexOf('.');
  let nameOnly, ext;
  if (dotIndex >= 0) {
    nameOnly = filename.slice(0, dotIndex);              // e.g. "VeryLongName…"
    ext = filename.slice(dotIndex);                       // e.g. ".jpg"
  } else {
    nameOnly = filename;                                  // no extension
    ext = '';
  }

  // 5) Truncate nameOnly if it exceeds MAX_NAME_LEN
  if (nameOnly.length > MAX_NAME_LEN) {
    nameOnly = nameOnly.slice(0, MAX_NAME_LEN);
  }

  // 6) Build the new filename: zero-padded index + "_" + truncated nameOnly + ext
  const prefix = String(index + 1).padStart(2, '0');      // "01", "02", ...
  const newName = `${prefix}_${nameOnly}${ext}`;          // e.g. "03_VeryLongName…jpg"

  // 7) Reassemble: directory + new filename
  return dir + newName;
});
    currentImagePaths = renamedPaths;
  } else {
    currentImagePaths = sortedPaths;
  }

  // 3) Re-render thumbnails (force-clear then render)
  console.log('[renderer] Now rendering:', currentImagePaths);
  renderThumbnails([]);
  setTimeout(() => renderThumbnails(currentImagePaths), 10);

  btnSortPrompt.innerText = 'Sort by Prompt…';
  btnSortPrompt.disabled = false;
}
catch (err) {
    console.error('Error during sort:', err);
    alert('An error occurred while sorting or renaming. Check the console for details.');
  } finally {
    btnSortPrompt.innerText = 'Sort by Prompt…';
    btnSortPrompt.disabled = false;
  }
}

);
btnSortConcept.addEventListener('click', async () => {
  if (!currentFolder || currentImagePaths.length === 0) return;

  // 1) Ask for the three pieces: dimension / start / end
  const dimension = await showPrompt();
  if (!dimension) return;

  const orderStart = await showPrompt();
  if (!orderStart) return;

  const orderEnd = await showPrompt();
  if (!orderEnd) return;

  btnSortConcept.innerText = 'Sorting…';
  btnSortConcept.disabled = true;

  try {
    // Send to your new conceptSort IPC
    const sortedPaths = await window.electronAPI.conceptSort({
      imagePaths: currentImagePaths,
      dimension,
      orderStart,
      orderEnd
    });

    if (!Array.isArray(sortedPaths)) {
      throw new Error('conceptSort did not return an array');
    }

    // (Optionally skip the rename prompt for concept sort,
    //  since renaming files by content-tag is unusual. If you
    //  want the same rename logic, you can copy from above.)
    currentImagePaths = sortedPaths;

    // Now re-render in one shot
    renderThumbnails([]);
    setTimeout(() => renderThumbnails(currentImagePaths), 10);
  } catch (err) {
    console.error('Error during concept sort:', err);
    alert('An error occurred while sorting by concept. See console for details.');
  } finally {
    btnSortConcept.innerText = 'Sort by Concept…';
    btnSortConcept.disabled = false;
  }
});


