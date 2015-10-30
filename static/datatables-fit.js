$(document).ready(function() {
    $('#datatables-fit').DataTable({
        "paging": false
    });
    $('table.datatables').DataTable({
        "lengthMenu": [[20, 50, 75, 100, -1], [20, 50, 75, 100, "All"]]
    });
} );