$(document).ready(function() {
    $('#custom').DataTable({
        "lengthMenu": [[50, 75, 100, -1], [50, 75, 100, "All"]]
    });
    $('table.datatables').DataTable({
        "lengthMenu": [[20, 50, 75, 100, -1], [20, 50, 75, 100, "All"]]
    });
} );