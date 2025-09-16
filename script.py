import fitz  # PyMuPDF is imported as 'fitz'
import os

def extract_text_from_pdf(pdf_path, output_txt_path):
    """
    Extracts text from a PDF file and saves it to a text file.

    Args:
        pdf_path (str): The path to the input PDF file.
        output_txt_path (str): The path to the output text file.
    """
    try:
        # Open the PDF file
        with fitz.open(pdf_path) as pdf_document:
            print(f"Opened PDF: {pdf_path}")
            
            # Initialize an empty string to store all extracted text
            full_text = ""
            
            # Iterate through each page in the PDF
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                # Extract text from the current page
                page_text = page.get_text()
                # Append the extracted text to the main string, adding a page break for clarity
                full_text += page_text + "\n--- Page End ---\n"
            
        # Write the full extracted text to the output file
        with open(output_txt_path, 'w', encoding='utf-8') as output_file:
            output_file.write(full_text)
            
        print(f"Successfully extracted text to: {output_txt_path}")
        
    except fitz.FileNotFoundError:
        print(f"Error: The file '{pdf_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Define the input PDF file name and the output text file name
    # You MUST change 'your_document.pdf' to the actual name of your file.
    # Make sure the PDF file is in the same directory as this script.
    pdf_file_name = "your_document.pdf"
    txt_file_name = "extracted_text.txt"
    
    # Check if the input PDF file exists
    if os.path.exists(pdf_file_name):
        extract_text_from_pdf(pdf_file_name, txt_file_name)
    else:
        print(f"The file '{pdf_file_name}' does not exist. Please place your PDF in the same folder and update the script's `pdf_file_name` variable.")
