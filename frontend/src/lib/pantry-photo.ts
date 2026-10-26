/** Resize camera/library images before upload; strips EXIF including location. */
export async function preparePantryPhoto(file: File): Promise<Blob> {
	if (file.size > 25 * 1024 * 1024) throw new Error('Choose a photo smaller than 25 MB.');
	const url = URL.createObjectURL(file);
	try {
		const image = new Image();
		image.src = url;
		await image.decode();
		if (image.naturalWidth * image.naturalHeight > 25_000_000) throw new Error('Choose a photo up to 25 megapixels.');
		const scale = Math.min(1, 2048 / Math.max(image.naturalWidth, image.naturalHeight));
		const canvas = document.createElement('canvas');
		canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
		canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
		const context = canvas.getContext('2d');
		if (!context) throw new Error('Could not prepare this photo.');
		context.fillStyle = '#fff';
		context.fillRect(0, 0, canvas.width, canvas.height);
		context.drawImage(image, 0, 0, canvas.width, canvas.height);
		return await new Promise<Blob>((resolve, reject) => canvas.toBlob(
			blob => blob ? resolve(blob) : reject(new Error('Could not prepare this photo.')), 'image/jpeg', 0.85));
	} catch (error) {
		if (error instanceof Error && !(error instanceof DOMException)) throw error;
		throw new Error('This browser could not read the photo. Try a JPEG or take a new photo.');
	} finally { URL.revokeObjectURL(url); }
}
