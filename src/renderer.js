// src/renderer.js

let currentFolder = null;
let currentImagePaths = [];

const btnChooseFolder = document.getElementById('btnChooseFolder');
const txtFolderPath   = document.getElementById('txtFolderPath');
const btnSortPrompt   = document.getElementById('btnSortPrompt');
const gridContainer   = document.getElementById('thumbnail-grid');

// Modal elements
const promptModal = document.getElementById('promptModal');
const promptInput = document.getElementById('promptInput');
const promptOk    = document.getElementById('promptOk');
const promptCancel = document.getElementById('promptCancel');

/**
 * Returns a Promise that resolves to the user’s input string
 * when they click OK, or null if they click Cancel.
 */
function showPrompt() {
  return new Promise((resolve) => {
    // Show the modal
    promptInput.value = '';           // clear previous text
    promptModal.style.display = 'flex';
    promptInput.focus();

    // Handler for OK
    function onOk() {
      cleanup();
      resolve(promptInput.value.trim());
    }

    // Handler for Cancel (or clicking outside? You could add backdrop clicks if you want)
    function onCancel() {
      cleanup();
      resolve(null);
    }

    // When the user clicks “OK”
    promptOk.addEventListener('click', onOk);

    // When the user clicks “Cancel”
    promptCancel.addEventListener('click', onCancel);

    // If they press Enter while focused on the input, treat as OK
    function onKeyDown(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        onOk();
      } else if (e.key === 'Escape') {
        // ESC ⇒ cancel
        e.preventDefault();
        onCancel();
      }
    }
    promptInput.addEventListener('keydown', onKeyDown);

    // Remove listeners and hide modal
    function cleanup() {
      promptOk.removeEventListener('click', onOk);
      promptCancel.removeEventListener('click', onCancel);
      promptInput.removeEventListener('keydown', onKeyDown);
      promptModal.style.display = 'none';
    }
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
  renderThumbnails(currentImagePaths);
});

/** “Sort by Prompt” button handler */
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
    currentImagePaths = sortedPaths;
    renderThumbnails(currentImagePaths);
  } catch (err) {
    console.error('Error during sort:', err,currentImagePaths);
    alert('An error occurred while sorting. Check the console for details.');
  } finally {
    btnSortPrompt.innerText = 'Sort by Prompt…';
    btnSortPrompt.disabled = false;
  }
});
