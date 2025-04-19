#!/usr/bin/env python3
"""
Enhanced PDF text extraction and cleaning tool with:
- Improved footnote removal
- Section header tagging (ABSTRACT/INTRODUCTION/CONCLUSION)
- Advanced whitespace normalization
- Hyphenation repair
- Header/footer detection
"""

import re
import os
import logging
import unicodedata
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_processing.log'),
        logging.StreamHandler()
    ]
)

class PDFProcessor:
    """Enhanced PDF processing with academic-focused cleaning."""
    
    # Bluebook citation patterns (expanded)
    BLUEBOOK_PATTERNS = [
        r'\b\d+ [A-Z]{1,3}\. [A-Z][a-z]+\. [A-Z][a-z]+\. \d+',
        r'[A-Z][a-zA-Z.-]+, [^,]+ \d+-\d+ \(\d{4}\)',
        r'https?://[^\s]+\[https://perma\.cc/[A-Z0-9-]+\]',
        r'\d+ [A-Z]{1,3}\.C\. § \d+[A-Z]*(?: \(\d{4}\))?',
        r'\d+ [A-Z]{1,3}\.F\.R\. (?:pt\.|§) \d+',
    ]
    
    # Footnote detection (enhanced)
    FOOTNOTE_INDICATORS = [
        'accessed \d{1,2} [A-Za-z]+ \d{4}',
        'available at <[^>]+>',
        'id\.', 'ibid\.', 'supra note', 'infra note',
        'cf\.', 'e\.g\.,', 'see, e\.g\.,',
        'retrieved from', 'last (?:visited|updated)'
    ]
    
    # Section headers to tag (exact uppercase match)
    SECTION_TAGS = {
        'Abstract': '[ABSTRACT]',
        'ABSTRACT': '[ABSTRACT]',
        'Introduction': '[INTRODUCTION]',
        'INTRODUCTION': '[INTRODUCTION]',
        'Conclusion': '[CONCLUSION]',
        'CONCLUSION': '[CONCLUSION]'
    }
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._compile_patterns()
        
    def _compile_patterns(self):
        """Compile all regex patterns once at init."""
        self.citation_pattern = re.compile(
            '|'.join(self.BLUEBOOK_PATTERNS),
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        self.footnote_pattern = re.compile(
            r'(?:^|\n)\s*([*‡†§]|\d+\.?)\s+.*?(?:' + 
            '|'.join(self.FOOTNOTE_INDICATORS) + ').*?(?=\n|$)',
            flags=re.IGNORECASE | re.MULTILINE
        )
        
        self.url_pattern = re.compile(
            r'<?(?:https?|www)\S+>?',
            flags=re.IGNORECASE
        )
        
        self.section_header_pattern = re.compile(
            r'^(?P<header>' + '|'.join(re.escape(k) + r'\b' for k in self.SECTION_TAGS.keys()) + ')',
            flags=re.MULTILINE
        )
    
    def extract_text(self, pdf_path: Path) -> Optional[str]:
        """Improved text extraction with layout preservation."""
        try:
            text = ""
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    # Get text with minimal formatting
                    page_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES)
                    
                    # Simple header/footer detection (top/bottom 10% of page)
                    if len(page_text.splitlines()) > 10:
                        lines = page_text.splitlines()
                        body_lines = lines[2:-2]  # Skip first/last 2 lines
                        page_text = "\n".join(body_lines)
                    
                    text += page_text + "\n"
            return text if text.strip() else None
        except Exception as e:
            logging.error(f"Extraction failed for {pdf_path}: {str(e)}")
            return None
    
    def _repair_hyphenation(self, text: str) -> str:
        """Rejoin words split by hyphen+newline."""
        return re.sub(
            r'([a-z])-\s*\n\s*([a-z])', 
            r'\1\2', 
            text, 
            flags=re.IGNORECASE
        )
    
    def _normalize_whitespace(self, text: str) -> str:
        """Clean up whitespace while preserving paragraphs."""
        # Preserve intentional paragraph breaks
        text = re.sub(r'(\S)\n\n(\S)', r'\1\n\n\2', text)
        # Remove mid-paragraph line breaks
        text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
        # Collapse multiple spaces
        return re.sub(r'[ \t]+', ' ', text)
    
    def _tag_section_headers(self, text: str) -> str:
        """Convert section headers to tagged format."""
        def replace_match(match):
            header = match.group('header')
            return self.SECTION_TAGS.get(header, header)
        
        return self.section_header_pattern.sub(replace_match, text)
    
    def remove_citations(self, text: str) -> str:
        """Enhanced citation/footnote removal."""
        try:
            # Remove standard citations
            text = self.citation_pattern.sub('', text)
            
            # Remove footnotes with markers
            text = self.footnote_pattern.sub('', text)
            
            # Remove orphaned footnote markers
            text = re.sub(
                r'^\s*[*‡†§]|\d+\.?\s*$', 
                '', 
                text, 
                flags=re.MULTILINE
            )
            
            return text
        except Exception as e:
            logging.error(f"Citation removal error: {str(e)}")
            return text
    
    def clean_text(self, text: str) -> str:
        """Comprehensive text normalization pipeline."""
        try:
            # Normalize Unicode first
            text = unicodedata.normalize('NFKC', text)
            
            # Repair hyphenated words before other processing
            text = self._repair_hyphenation(text)
            
            # Remove URLs
            text = self.url_pattern.sub('', text)
            
            # Tag section headers (must be before whitespace normalization)
            text = self._tag_section_headers(text)
            
            # Normalize whitespace and punctuation
            text = self._normalize_whitespace(text)
            
            # Standardize quotes/dashes
            text = text.replace('“', '"').replace('”', '"')
            text = text.replace('‘', "'").replace('’', "'")
            text = text.replace('—', '--')
            
            # Final cleanup
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        except Exception as e:
            logging.error(f"Text cleaning failed: {str(e)}")
            return text
    
    def process_pdf(self, pdf_path: Path, output_dir: Path) -> bool:
        """Enhanced processing pipeline."""
        try:
            # Extract text with improved layout handling
            raw_text = self.extract_text(pdf_path)
            if not raw_text:
                return False
            
            # Apply cleaning pipeline
            cleaned_text = self.remove_citations(raw_text)
            cleaned_text = self.clean_text(cleaned_text)
            
            # Validate output
            if not cleaned_text.strip():
                logging.warning(f"Empty output for {pdf_path}")
                return False
            
            # Save results
            output_path = output_dir / f'{pdf_path.stem}_cleaned.txt'
            output_path.write_text(cleaned_text, encoding='utf-8')
            return True
        except Exception as e:
            logging.error(f"Processing failed for {pdf_path}: {str(e)}")
            return False
    
    def process_directory(self, input_dir: Path, output_dir: Path) -> Tuple[int, int]:
        """
        Process all PDFs in input_dir, save cleaned text files to output_dir.
        Returns tuple of (success_count, failure_count).
        """
        # Ensure directories exist
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Get PDF files
        pdf_files = list(input_dir.glob('*.pdf'))
        if not pdf_files:
            logging.warning(f"No PDF files found in {input_dir}")
            return (0, 0)
        
        # Process files (optionally in parallel)
        success_count = 0
        failure_count = 0
        
        if self.max_workers > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self.process_pdf, pdf, output_dir): pdf
                    for pdf in pdf_files
                }
                
                for future in as_completed(futures):
                    pdf = futures[future]
                    try:
                        if future.result():
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logging.error(f"Error processing {pdf}: {str(e)}")
                        failure_count += 1
        else:
            for pdf in pdf_files:
                if self.process_pdf(pdf, output_dir):
                    success_count += 1
                else:
                    failure_count += 1
        
        return (success_count, failure_count)


def main():
    """Command-line interface for the PDF processor."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert PDFs to cleaned text files with citation removal'
    )
    parser.add_argument(
        '-i', '--input', 
        default='./pdfs',
        help='Input directory containing PDF files (default: ./pdfs)'
    )
    parser.add_argument(
        '-o', '--output',
        default='./cleaned_texts',
        help='Output directory for cleaned text files (default: ./cleaned_texts)'
    )
    parser.add_argument(
        '-j', '--jobs',
        type=int,
        default=4,
        help='Number of parallel workers to use (default: 4)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    processor = PDFProcessor(max_workers=args.jobs)
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    logging.info(f"Processing PDFs in {input_dir}...")
    success, failures = processor.process_directory(input_dir, output_dir)
    
    logging.info(
        f"Processing complete. Success: {success}, Failures: {failures}. "
        f"Output saved to {output_dir}"
    )
    
    if failures > 0:
        logging.warning(
            f"{failures} files failed to process. Check the log for details."
        )


if __name__ == '__main__':
    main()